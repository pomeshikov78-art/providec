"""Валидаторы реквизитов (методики ФНС) — перенос алгоритмов, проверенных в прототипе v8
(заимствованы из прототипа-аналога АССПР v2.4)."""
from __future__ import annotations


def inn_valid(v: str) -> bool:
    """Контрольная сумма ИНН (10 или 12 цифр, методика ФНС)."""
    v = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(v) == 10:
        c = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        s = sum(c[i] * int(v[i]) for i in range(9))
        return (s % 11) % 10 == int(v[9])
    if len(v) == 12:
        c1 = [7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        c2 = [3, 7, 2, 4, 10, 3, 5, 9, 4, 6, 8]
        s1 = sum(c1[i] * int(v[i]) for i in range(10))
        s2 = sum(c2[i] * int(v[i]) for i in range(11))
        return (s1 % 11) % 10 == int(v[10]) and (s2 % 11) % 10 == int(v[11])
    return False


def inn_fix(v: str) -> str:
    """Нормализация ИНН: пересчёт контрольной цифры по первым 9."""
    v = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(v) in (9, 10):
        c = [2, 4, 10, 3, 5, 9, 4, 6, 8]
        s = sum(c[i] * int(v[i]) for i in range(9))
        return v[:9] + str((s % 11) % 10)
    return v


def ogrn_valid(v: str) -> bool:
    """Контрольное число ОГРН (13) / ОГРНИП (15)."""
    v = "".join(ch for ch in (v or "") if ch.isdigit())
    if len(v) not in (13, 15):
        return False
    base = int(v[:-1])
    r = base % 11
    if r > 9:
        r %= 10
    return r == int(v[-1])
