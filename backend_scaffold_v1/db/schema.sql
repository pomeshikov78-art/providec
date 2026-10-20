-- ============================================================================
-- АИС «Техноконтур» (шифр «Провидец») · схема БД · Postgres Pro + PostGIS
-- Фаза 1 (ADR-001). Названия и состав сущностей соответствуют контрактам
-- openapi.yaml / asyncapi.yaml и спецификации Приложения 2 к ТЗ (92 поля).
-- ============================================================================
CREATE EXTENSION IF NOT EXISTS postgis;
CREATE EXTENSION IF NOT EXISTS pgcrypto;

-- ---------- Перечисления ----------
CREATE TYPE org_type        AS ENUM ('ent','nio','test');
CREATE TYPE passport_status AS ENUM ('draft','pending','verified');
CREATE TYPE gate_status     AS ENUM ('go','no-go','review');
CREATE TYPE comp_key        AS ENUM ('sci','des','prod','test','dig','mng');
CREATE TYPE sev_level       AS ENUM ('info','warn','alert');
CREATE TYPE module_status   AS ENUM ('active','disabled','degraded','error');

-- ---------- IAM ----------
CREATE TABLE users (
  id           uuid PRIMARY KEY DEFAULT gen_random_uuid(),
  login        text UNIQUE NOT NULL,
  fio          text NOT NULL,
  role_level   text NOT NULL CHECK (role_level ~ '^L[0-7]$'),
  org_id       text,                       -- ABAC-атрибут для L4 (своё предприятие)
  mfa_enabled  boolean NOT NULL DEFAULT false,
  active       boolean NOT NULL DEFAULT true,
  created_at   timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE users IS 'Учетные записи; роль L0–L7 (ТЗ п.3.2); ЕСИА — вариант А';

CREATE TABLE iam_policies (
  id            serial PRIMARY KEY,
  subject_role  text NOT NULL,              -- L0..L7 или '*'
  action        text NOT NULL,              -- admin|gate|org.write|org.create|expert.approve|report.run|view...
  resource      text NOT NULL DEFAULT '*',
  effect        text NOT NULL DEFAULT 'deny' CHECK (effect IN ('allow','deny')),
  condition     jsonb,                      -- ABAC: {"org_eq_subject": true} и т.п.
  note          text
);

-- ---------- Ядро ----------
CREATE TABLE module_registry (
  code        text PRIMARY KEY,             -- MOD-PASS ...
  name        text NOT NULL,
  required    boolean NOT NULL,
  version     text NOT NULL,                -- SemVer
  deps        text[] NOT NULL DEFAULT '{}',
  status      module_status NOT NULL DEFAULT 'active',
  updated_at  timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE events_log (
  id      bigserial PRIMARY KEY,
  ts      timestamptz NOT NULL DEFAULT now(),
  type    text NOT NULL,
  source  text NOT NULL,
  payload text,
  sev     sev_level NOT NULL DEFAULT 'info',
  trace_id uuid
) PARTITION BY RANGE (ts);
CREATE TABLE events_log_default PARTITION OF events_log DEFAULT;
CREATE INDEX ON events_log (type, ts DESC);
COMMENT ON TABLE events_log IS 'Журнал шины событий (каталог — asyncapi.yaml); партиционирование по месяцам';

CREATE TABLE audit_log (
  id         bigserial PRIMARY KEY,
  ts         timestamptz NOT NULL DEFAULT now(),
  user_login text NOT NULL,
  role_level text,
  action     text NOT NULL,
  object     text,
  result     text,
  ip         inet,
  prev_hash  char(64),
  hash       char(64) NOT NULL
);
COMMENT ON TABLE audit_log IS 'WORM: hash-chain (sha256). UPDATE/DELETE запрещены триггером.';

CREATE OR REPLACE FUNCTION audit_no_modification() RETURNS trigger AS $$
BEGIN RAISE EXCEPTION 'audit_log is append-only (WORM)'; END;
$$ LANGUAGE plpgsql;
CREATE TRIGGER audit_worm BEFORE UPDATE OR DELETE ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_no_modification();

CREATE OR REPLACE FUNCTION audit_chain() RETURNS trigger AS $$
BEGIN
  SELECT hash INTO NEW.prev_hash FROM audit_log ORDER BY id DESC LIMIT 1;
  IF NEW.prev_hash IS NULL THEN NEW.prev_hash := repeat('0',64); END IF;
  NEW.hash := encode(digest(NEW.prev_hash || NEW.ts || NEW.user_login || NEW.action
               || coalesce(NEW.object,'') || coalesce(NEW.result,''), 'sha256'), 'hex');
  RETURN NEW;
END; $$ LANGUAGE plpgsql;
CREATE TRIGGER audit_hash_chain BEFORE INSERT ON audit_log
  FOR EACH ROW EXECUTE FUNCTION audit_chain();

-- ---------- Предприятия и паспорта (MOD-PASS) ----------
CREATE TABLE organizations (
  id          text PRIMARY KEY,             -- E01...
  name        text NOT NULL,
  short_name  text NOT NULL,
  org_type    org_type NOT NULL,
  city        text NOT NULL,
  region      text NOT NULL,                -- федеральный округ
  geom        geometry(Point, 4326),        -- PostGIS (MOD-GEO)
  lat         numeric(9,6) NOT NULL,
  lon         numeric(9,6) NOT NULL,
  inn         char(10) NOT NULL,
  inn_valid   boolean NOT NULL DEFAULT false,  -- пересчитывается сервисом валидации ФНС (контрольные суммы)
  founded     smallint,
  employees   integer,
  revenue     numeric(12,2),                -- млрд ₽
  status      passport_status NOT NULL DEFAULT 'draft',
  lc_stage    smallint NOT NULL DEFAULT 0 CHECK (lc_stage BETWEEN 0 AND 8),
  created_at  timestamptz NOT NULL DEFAULT now(),
  updated_at  timestamptz NOT NULL DEFAULT now()
);
CREATE INDEX ON organizations USING gist (geom);
CREATE INDEX ON organizations (region, org_type);

CREATE TABLE passport_sections (
  n          smallint PRIMARY KEY CHECK (n BETWEEN 1 AND 12),
  name       text NOT NULL,
  threshold  smallint NOT NULL              -- минимальный порог полноты, Прил. 2.14
);

CREATE TABLE passport_fields (
  id          serial PRIMARY KEY,
  section_n   smallint NOT NULL REFERENCES passport_sections(n),
  ord         smallint NOT NULL,
  name        text NOT NULL,
  ftype       text NOT NULL,                -- Текст|Число|Список|Файлы|Справочник|Матрица|Ссылки|Журнал
  required    boolean NOT NULL,
  source      text,                         -- источник автозаполнения (ЕГРЮЛ, ГИСП...) — раздел 1
  UNIQUE (section_n, ord)
);
COMMENT ON TABLE passport_fields IS 'Спецификация 92 полей цифрового паспорта (Приложение 2 к ТЗ)';

CREATE TABLE passport_values (
  org_id      text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  field_id    integer NOT NULL REFERENCES passport_fields(id),
  value       text,
  updated_by  text,
  updated_at  timestamptz NOT NULL DEFAULT now(),
  PRIMARY KEY (org_id, field_id)
);

CREATE TABLE passport_versions (
  id          bigserial PRIMARY KEY,
  org_id      text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  ver_n       integer NOT NULL,
  changes     jsonb NOT NULL DEFAULT '[]',  -- [{section, field, old, new}, ...]
  crc32       char(10) NOT NULL,            -- снимок целостности (как в прототипе: 0x........)
  author      text NOT NULL,
  role_level  text,
  created_at  timestamptz NOT NULL DEFAULT now(),
  UNIQUE (org_id, ver_n)
);
COMMENT ON TABLE passport_versions IS 'Хранение ≥ 10 версий (Задача 1.5 ТЗ)';

CREATE TABLE passport_files (
  id          bigserial PRIMARY KEY,
  org_id      text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  section_n   smallint REFERENCES passport_sections(n),
  title       text NOT NULL,
  storage_key text NOT NULL,                -- MinIO (S3) object key
  size_bytes  bigint,
  sign_status text NOT NULL DEFAULT 'unsigned', -- unsigned|signed(ЭЦП ГОСТ Р 34.10-2012)|verified
  uploaded_at timestamptz NOT NULL DEFAULT now()
);

-- ---------- Профили, компетенции, двойники (MOD-PROF / MOD-COMP) ----------
CREATE TABLE org_competencies (
  org_id   text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  comp     comp_key NOT NULL,
  level    smallint NOT NULL CHECK (level BETWEEN 0 AND 100),
  PRIMARY KEY (org_id, comp)
);

CREATE TABLE org_radar (
  org_id   text NOT NULL REFERENCES organizations(id) ON DELETE CASCADE,
  dim      smallint NOT NULL CHECK (dim BETWEEN 1 AND 7), -- Наука..Цифровизация
  val      smallint NOT NULL CHECK (val BETWEEN 0 AND 100),
  PRIMARY KEY (org_id, dim)
);

CREATE TABLE maturity (
  org_id     text PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  trl        smallint NOT NULL CHECK (trl BETWEEN 1 AND 9),
  mrl        smallint NOT NULL CHECK (mrl BETWEEN 1 AND 10),
  irl        smallint NOT NULL CHECK (irl BETWEEN 1 AND 9),
  index_i    numeric(4,1) GENERATED ALWAYS AS
             (round((0.4*trl/9.0 + 0.35*mrl/10.0 + 0.25*irl/9.0)*100, 1)) STORED,
  calc_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE maturity IS 'I = (0,4·TRL/9 + 0,35·MRL/10 + 0,25·IRL/9)×100 (Прил. 3.5)';

CREATE TABLE twins (
  org_id      text PRIMARY KEY REFERENCES organizations(id) ON DELETE CASCADE,
  crc32       char(10) NOT NULL,
  snapshot    jsonb NOT NULL,
  index_i     numeric(4,1),
  gaps_count  smallint NOT NULL DEFAULT 0,
  built_at    timestamptz NOT NULL DEFAULT now()
);
COMMENT ON TABLE twins IS 'Цифровые двойники управленческого состояния (ТЗ п.2.1)';

-- ---------- НИОКР (MOD-NIOKR / MOD-PORTF) ----------
CREATE TABLE projects (
  id           text PRIMARY KEY,            -- P01...
  name         text NOT NULL,
  org_id       text NOT NULL REFERENCES organizations(id),
  lc_stage     smallint NOT NULL DEFAULT 0 CHECK (lc_stage BETWEEN 0 AND 8),
  gate         gate_status NOT NULL DEFAULT 'review',
  deadline     date,
  budget       numeric(10,2),               -- млрд ₽
  trl_target   smallint,
  trl_current  smallint,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE project_gates (                -- append-only: решения контрольных точек
  id           bigserial PRIMARY KEY,
  project_id   text NOT NULL REFERENCES projects(id),
  stage        smallint NOT NULL,
  decision     gate_status NOT NULL,
  comment      text,
  decided_by   text NOT NULL,
  decided_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE evm_snapshots (
  id          bigserial PRIMARY KEY,
  project_id  text NOT NULL REFERENCES projects(id),
  pv          numeric(10,3), ev numeric(10,3), ac numeric(10,3),
  spi         numeric(5,2),  cpi numeric(5,2),
  calc_at     timestamptz NOT NULL DEFAULT now()
);

-- ---------- Риски, документы, стимулы, экспертиза ----------
CREATE TABLE risks (
  id           text PRIMARY KEY,
  title        text NOT NULL,
  category     text NOT NULL,
  prob         smallint NOT NULL CHECK (prob BETWEEN 1 AND 5),
  impact       smallint NOT NULL CHECK (impact BETWEEN 1 AND 5),
  score        smallint GENERATED ALWAYS AS (prob*impact) STORED,
  owner_module text,
  status       text NOT NULL DEFAULT 'open',
  mitigation   text
);

CREATE TABLE documents (
  id           text PRIMARY KEY,
  title        text NOT NULL,
  org_id       text REFERENCES organizations(id),
  kind         text NOT NULL,
  sign_status  text NOT NULL DEFAULT 'draft',
  doc_date     date,
  storage_key  text,
  created_at   timestamptz NOT NULL DEFAULT now()
);

CREATE TABLE stims (
  id           text PRIMARY KEY,
  org_id       text REFERENCES organizations(id),
  kind         text NOT NULL CHECK (kind IN ('stim','sanction')),
  title        text NOT NULL,
  basis        text,
  doc_date     date,
  status       text NOT NULL DEFAULT 'active'
);

CREATE TABLE expert_queue (
  id           text PRIMARY KEY,
  org_id       text REFERENCES organizations(id),
  object       text NOT NULL,
  expert       text,
  since        date NOT NULL DEFAULT current_date,
  priority     text NOT NULL DEFAULT 'Средний',
  status       text NOT NULL DEFAULT 'queued'
);

-- ---------- Интеграции (MOD-INT) ----------
CREATE TABLE integrations (
  code          text PRIMARY KEY,
  name          text NOT NULL,
  grp           text NOT NULL,
  protocol      text,
  period        text,
  variant_a     boolean NOT NULL DEFAULT true,   -- доступна в варианте А
  variant_b_mode text NOT NULL DEFAULT 'manual'  -- manual | exchange | unavailable
);

CREATE TABLE asspr_packages (
  id            text PRIMARY KEY,           -- АССПР-2026-0142
  org_name      text NOT NULL,
  target_org_id text REFERENCES organizations(id),
  ver           text,
  doc_date      date,
  approval      text,
  completeness  smallint,
  issues        smallint DEFAULT 0,
  note          text,
  payload       jsonb NOT NULL,             -- секции, компетенции, TRL/MRL/IRL
  imported_at   timestamptz,
  imported_by   text
);

-- ============================================================================
-- SEED: справочные данные (перенесены из прототипа v8.0.0)
-- ============================================================================
INSERT INTO module_registry (code,name,required,version,deps) VALUES
 ('MOD-PASS','Цифровой паспорт предприятия',true,'4.0.3','{}'),
 ('MOD-PROF','Цифровой профиль и аналитика',true,'4.0.2','{MOD-PASS,MOD-COMP}'),
 ('MOD-NIOKR','Управление жизненным циклом НИОКР',true,'4.0.5','{MOD-PASS}'),
 ('MOD-COMP','Оценка компетенций и зрелости',true,'4.0.1','{MOD-PASS}'),
 ('MOD-REPORT','Отчетность и дашборды',true,'4.0.4','{MOD-PROF,MOD-KPI}'),
 ('MOD-GEO','Геоподдержка и геоаналитика',true,'4.0.6','{MOD-PASS,MOD-PROF}'),
 ('MOD-EXPERT','Экспертная оценка и верификация',false,'3.9.2','{MOD-PASS}'),
 ('MOD-PORTF','Портфель проектов и программ',false,'3.8.7','{MOD-NIOKR}'),
 ('MOD-RISK','Управление рисками',false,'3.9.0','{MOD-PROF}'),
 ('MOD-COOP','Поиск кооперации и матчинг',false,'3.9.4','{MOD-PROF,MOD-GEO}'),
 ('MOD-INT','Интеграционный шлюз',false,'4.0.0','{}'),
 ('MOD-AI','ИИ-рекомендации и прогнозирование',false,'3.7.5','{MOD-PROF,MOD-NIOKR}'),
 ('MOD-DOC','Электронный документооборот',false,'3.8.1','{MOD-PASS}'),
 ('MOD-STIM','Стимулы и санкции',false,'3.6.9','{MOD-KPI}'),
 ('MOD-KPI','Показатели эффективности',false,'4.0.1','{MOD-PROF}');

INSERT INTO passport_sections (n,name,threshold) VALUES
 (1,'Идентификационные сведения',95),
 (2,'Организационная структура',90),
 (3,'Кадровый и научный потенциал',90),
 (4,'Компетентностный профиль',95),
 (5,'Технологический профиль',95),
 (6,'Научно-технологический задел',85),
 (7,'Производственный профиль',90),
 (8,'Испытательный потенциал',85),
 (9,'НИОКР-профиль',90),
 (10,'Финансово-инвестиционный паспорт',90),
 (11,'Производственный и экономический результат',90),
 (12,'Документальная доказательность',95);

-- Политики IAM (перенос can() из прототипа v8.0.0)
INSERT INTO iam_policies (subject_role,action,resource,effect,condition,note) VALUES
 ('*','view','*','allow',NULL,'L0–L7: просмотр агрегированных данных согласно роли'),
 ('L7','admin','*','allow',NULL,'Управление конфигурацией, модулями, импортом, хранилищем'),
 ('L6','admin','*','allow',NULL,'Делегированные полномочия'),
 ('L1','gate','projects/*','allow',NULL,'Госорганы: решения по контрольным точкам'),
 ('L2','gate','projects/*','allow',NULL,'Отраслевые органы'),
 ('L5','gate','projects/*','allow',NULL,'НИОКР/испытания'),
 ('L5','expert.approve','*','allow',NULL,'Экспертиза и верификация'),
 ('L7','expert.approve','*','allow',NULL),
 ('L4','org.write','orgs/{org_id}/passport','allow','{"org_eq_subject":true}','ABAC: только собственное предприятие'),
 ('L4','admin','*','deny',NULL,'Предприятие не управляет конфигурацией'),
 ('L0','org.write','*','deny',NULL,'Внешний пользователь — только просмотр'),
 ('L3','org.write','*','deny',NULL,'Партнеры/инвесторы — только просмотр');

-- Спецификация 92 полей цифрового паспорта (Приложение 2 к ТЗ; seed из прототипа v8.0.0)
INSERT INTO passport_fields (section_n,ord,name,ftype,required,source) VALUES
 (1,1,'Полное наименование','Текст',true,'ЕГРЮЛ'),
 (1,2,'Сокращённое наименование','Текст',true,'ЕГРЮЛ'),
 (1,3,'ИНН','Число (10/12)',true,'ФНС'),
 (1,4,'ОГРН','Число (13/15)',true,'ФНС'),
 (1,5,'КПП','Число (9)',true,'ФНС'),
 (1,6,'Организационно-правовая форма','Справочник',true,'ЕГРЮЛ'),
 (1,7,'Отрасль (ОКВЭД основной)','Справочник',true,'ЕГРЮЛ'),
 (1,8,'Отрасль (ОКВЭД дополнительные)','Справочник',false,'ЕГРЮЛ'),
 (1,9,'Регион регистрации','Справочник',true,'ЕГРЮЛ'),
 (1,10,'Юридический адрес','Текст',true,'ЕГРЮЛ'),
 (1,11,'Фактический адрес','Текст',true,'Анкета'),
 (1,12,'Географические координаты','WGS84',true,'Анкета/ГИС'),
 (1,13,'Дата регистрации','Дата',true,'ЕГРЮЛ'),
 (1,14,'Статус (действующее/ликвидируемое)','Справочник',true,'ЕГРЮЛ'),
 (1,15,'Сайт организации','URL',false,'Анкета'),
 (1,16,'Контактные данные','Текст',true,'Анкета'),
 (2,1,'Количество подразделений','Число',true,NULL),
 (2,2,'Перечень филиалов','Список',true,NULL),
 (2,3,'Руководители (ФИО, должность)','Список',true,NULL),
 (2,4,'Функции подразделений','Текст',true,NULL),
 (2,5,'Компетенции подразделений','Справочник',true,NULL),
 (2,6,'Связанные НИОКР','Ссылки',false,NULL),
 (2,7,'Материнская/дочерняя структура','Ссылки',false,NULL),
 (3,1,'Общая численность персонала','Число',true,NULL),
 (3,2,'Структура персонала (по категориям)','Список',true,NULL),
 (3,3,'Количество руководителей','Число',true,NULL),
 (3,4,'Ключевые компетенции','Справочник',true,NULL),
 (3,5,'Учёные степени (к.т.н., д.т.н.)','Число',true,NULL),
 (3,6,'Опыт работы (средний стаж)','Число',true,NULL),
 (3,7,'Доступность по уровням допуска','Справочник',true,NULL),
 (3,8,'Наличие молодых специалистов (< 35 лет)','Число',false,NULL),
 (3,9,'Программы подготовки кадров','Текст',false,NULL),
 (4,1,'Структура компетенций (6 направлений)','Матрица',true,NULL),
 (4,2,'Уровни владения компетенциями (0–5)','Число',true,NULL),
 (4,3,'Уровни зрелости (TRL/MRL/IRL)','Число',true,NULL),
 (4,4,'Оборудование и ресурсы','Список',true,NULL),
 (4,5,'Связь с проектами и экспертизой','Ссылки',true,NULL),
 (4,6,'Дефицитные компетенции','Список',true,NULL),
 (4,7,'Сертификаты и лицензии','Список',false,NULL),
 (5,1,'Текущие TRL/MRL/IRL','Число',true,NULL),
 (5,2,'IP и права на технологии','Список',true,NULL),
 (5,3,'Типы технологий','Справочник',true,NULL),
 (5,4,'Статус и риски технологий','Справочник',true,NULL),
 (5,5,'Технологические дорожные карты','Документ',false,NULL),
 (5,6,'Патентный портфель','Список',true,NULL),
 (6,1,'Патенты','Список',true,NULL),
 (6,2,'РИД (результаты интеллектуальной деятельности)','Список',true,NULL),
 (6,3,'ПО (программное обеспечение)','Список',true,NULL),
 (6,4,'Алгоритмы','Список',false,NULL),
 (6,5,'Образцы, прототипы, модели','Список',true,NULL),
 (6,6,'Datasets, методики','Список',false,NULL),
 (6,7,'Связь с технологиями','Ссылки',true,NULL),
 (7,1,'Площадки (адрес, площадь)','Список',true,NULL),
 (7,2,'Оборудование (перечень, состояние)','Список',true,NULL),
 (7,3,'Технологические линии','Список',true,NULL),
 (7,4,'Мощности (плановые/фактические)','Число',true,NULL),
 (7,5,'Серийность производства','Число',true,NULL),
 (7,6,'Кооперация (поставщики)','Список',true,NULL),
 (7,7,'Загрузка мощностей (%)','Число',true,NULL),
 (8,1,'Лаборатории (перечень)','Список',true,NULL),
 (8,2,'Стенды (характеристики)','Список',true,NULL),
 (8,3,'Оборудование (испытательное)','Список',true,NULL),
 (8,4,'Аккредитации','Список',true,NULL),
 (8,5,'Виды и методики испытаний','Список',true,NULL),
 (8,6,'Квалификация персонала','Список',true,NULL),
 (9,1,'Объёмы НИОКР (текущие/завершённые)','Число',true,NULL),
 (9,2,'Динамика НИОКР (по годам)','Список',true,NULL),
 (9,3,'Активные проекты','Список',true,NULL),
 (9,4,'Завершённые проекты','Список',true,NULL),
 (9,5,'Эффективность и сроки','Число',true,NULL),
 (9,6,'Инвестиции в НИОКР','Число',true,NULL),
 (9,7,'Источники финансирования','Список',true,NULL),
 (10,1,'Источники финансирования','Список',true,NULL),
 (10,2,'Инвестиции (по годам)','Число',true,NULL),
 (10,3,'Затраты (OPEX/CAPEX)','Число',true,NULL),
 (10,4,'Доходы (по годам)','Число',true,NULL),
 (10,5,'Доля собственных средств (%)','Число',true,NULL),
 (10,6,'Финансовые показатели (выручка, прибыль)','Число',true,NULL),
 (10,7,'Кредитная история','Справочник',false,NULL),
 (11,1,'Выручка (по продуктам)','Число',true,NULL),
 (11,2,'Объёмы производства','Число',true,NULL),
 (11,3,'Продукты (перечень)','Список',true,NULL),
 (11,4,'Внедрённые технологии','Список',true,NULL),
 (11,5,'Экономический эффект','Число',true,NULL),
 (11,6,'Новые рынки и продукты','Список',false,NULL),
 (11,7,'ROI, NPV','Число',true,NULL),
 (12,1,'Документы (учредительные)','Файлы',true,NULL),
 (12,2,'Отчёты (финансовые, технические)','Файлы',true,NULL),
 (12,3,'Протоколы (испытаний, экспертиз)','Файлы',true,NULL),
 (12,4,'Экспертные заключения','Файлы',true,NULL),
 (12,5,'Цепочка подтверждения','Ссылки',true,NULL),
 (12,6,'Версионность и аудит','Журнал',true,NULL);

-- Контроль: ожидается 92 строки
DO $$ DECLARE c int; BEGIN SELECT count(*) INTO c FROM passport_fields; IF c<>92 THEN RAISE EXCEPTION 'passport_fields seed: % vmesto 92', c; END IF; END $$;
