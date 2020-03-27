from pathlib import Path
import numpy as np
import argparse

_type_priorities = [  # In decreasing order
    Path,
    str,
    int,
    float,
    bool,
]


def _priority(o):
    p = next((i for i, t in enumerate(_type_priorities) if type(o) is t), None)
    if p is not None:
        return p
    p = next((i for i, t in enumerate(_type_priorities) if isinstance(o, t)), None)
    if p is not None:
        return p
    return len(_type_priorities)


def print_args(args: argparse.Namespace, parser=None):
    dt = args2dict(args, parser)
    print("Arguments:")
    for param, value in dt.items():
        print("{0}: {1}".format(param, value))
    print("")


def args2dict(args: argparse.Namespace, parser=None):
    args = vars(args)
    if parser is None:
        priorities = list(map(_priority, args.values()))
    else:
        all_params = [a.dest for g in parser._action_groups for a in g._group_actions]
        priority = lambda p: all_params.index(p) if p in all_params else len(all_params)
        priorities = list(map(priority, args.keys()))

    indices = np.lexsort((list(args.keys()), priorities))
    items = list(args.items())

    out = {items[i][0]: items[i][1] for i in indices}
    return out
