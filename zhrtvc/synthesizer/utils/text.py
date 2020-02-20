#!usr/bin/env python
# -*- coding: utf-8 -*-
# author: kuangdd
# date: 2020/2/18
"""
"""
from phkit import text2sequence, sequence2phoneme, phoneme2sequence
from phkit import symbol_chinese as symbols
from phkit.pinyin import split_pinyin, text2pinyin
from phkit.phoneme import shengyun2ph_dict
from phkit.sequence import pinyin2phoneme, change_diao


def text_to_sequence(src):
    """
    文本样例：ka3 er3 pu3 pei2 wai4 sun1 wan2 hua2 ti1 .
    :param src: str,拼音字符串
    :return: list,ID列表
    """
    pys = []
    for py in src.split():
        if py.isalnum():
            pys.append(py)
        else:
            pys.append((py,))
    phs = pinyin2phoneme(pys)
    phs = change_diao(phs)
    seq = phoneme2sequence(phs)
    return seq


def sequence_to_text(src):
    out = sequence2phoneme(src)
    return "".join(out)


if __name__ == "__main__":
    print(__file__)
    text = "ka3 er3 pu3 pei2 wai4 sun1 wan2 hua2 ti1 . "
    out = text_to_sequence(text)
    print(out)
    out = sequence_to_text(out)
    print(out)
