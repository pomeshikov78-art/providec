#!/usr/bin/env python3
# -*- coding: utf-8 -*-
"""Простой лексер JS-строк: ищет незакрытые строковые литералы (без учёта regex-literals)."""
import sys

def lex(path):
    src = open(path, encoding='utf-8').read()
    i = 0; n = len(src); state = 'code'; line = 1; col = 1
    while i < n:
        ch = src[i]
        if state == 'code':
            if ch == '/' and i+1 < n and src[i+1] == '/': state = 'lc'; i += 2; col += 2
            elif ch == '/' and i+1 < n and src[i+1] == '*': state = 'bc'; i += 2; col += 2
            elif ch in "'\"`": state = {'\'': 'sq', '"': 'dq', '`': 'tl'}[ch]; i += 1; col += 1
            else:
                i += 1
                if ch == '\n': line += 1; col = 1
                else: col += 1
        elif state == 'lc':
            i += 1
            if ch == '\n': state = 'code'; line += 1; col = 1
            else: col += 1
        elif state == 'bc':
            if ch == '*' and i+1 < n and src[i+1] == '/': i += 2; col += 2; state = 'code'
            else:
                i += 1
                if ch == '\n': line += 1; col = 1
                else: col += 1
        else:
            q = {'sq': "'", 'dq': '"', 'tl': '`'}[state]
            if ch == '\\': i += 2; col += 2; continue
            if ch == '\n' and state != 'tl':
                print(path + ': UNTERMINATED ' + state + ' string near line %d col %d' % (line, col))
                print('  context:', repr(src[max(0, i-120):i+50]))
                return False
            i += 1
            if ch == '\n': line += 1; col = 1
            else: col += 1
            if ch == q: state = 'code'
    print(path + ': lexer OK (end state: ' + state + ')')
    return True

ok = all([lex(p) for p in sys.argv[1:]])
sys.exit(0 if ok else 1)
