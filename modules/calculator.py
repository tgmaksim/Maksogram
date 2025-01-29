import builtins

from sympy import acot
from typing import Union
from math import floor, sqrt, factorial, sin, cos, tan, radians, pi, e, degrees, asin, acos, atan


def round(number, ndigits=0):
    return floor(number * 10 ** ndigits + 0.5) / 10 ** ndigits


def median(*args: int | float) -> int | float:
    args = list(args)
    for arg in args:
        if type(arg) != int and type(arg) != float:
            raise Exception()
    args = sorted(args)
    if len(args) % 2 == 0:
        return (args[len(args) // 2 - 1] + args[len(args) // 2]) / 2
    else:
        return args[len(args) // 2]


def dispersion(*args: int | float) -> int | float:
    args = list(args)
    for arg in args:
        if type(arg) != int and type(arg) != float:
            raise Exception()
    ave = sum(args) / len(args)
    args = [(i - ave) ** 2 for i in args]
    return sum(args) / len(args)


def average(*args: int | float) -> int | float:
    args = list(args)
    for arg in args:
        if type(arg) != int and type(arg) != float:
            raise Exception()
    return sum(args) / len(args)


def geometric_mean(*args: int | float) -> int | float:
    args = list(args)
    for arg in args:
        if type(arg) != int and type(arg) != float:
            raise Exception()
    return eval(" * ".join([str(i) for i in args])) ** (1/len(args))


functions = \
    {"sqrt": sqrt, "factorial": factorial, "round": round,
     "radians": radians, "pi": pi, "e": e, "degrees": degrees,
     "sin": lambda x: sin(radians(x)), "cos": lambda x: cos(radians(x)), "tan": lambda x: tan(radians(x)),
     "cot": lambda x: cos(radians(x)) / sin(radians(x)),
     "asin": lambda x: degrees(asin(x)), "acos": lambda x: degrees(acos(x)),
     "atan": lambda x: degrees(atan(x)), "acot": lambda x: degrees(eval(str(acot(x)))),
     "sinr": sin, "cosr": cos, "tanr": tan, "cotr": lambda x: cos(x) / sin(x),
     "asinr": asin, "acosr": acos, "atanr": atan, "acotr": lambda x: eval(str(acot(x))),
     "tg": lambda x: tan(radians(x)), "ctg": lambda x: cos(radians(x)) / sin(radians(x)),
     "atg": lambda x: degrees(atan(x)), "actg": lambda x: degrees(eval(str(acot(x)))),
     "tgr": tan, "ctgr": lambda x: cos(x) / sin(x),
     "atgr": atan, "actgr": lambda x: eval(str(acot(x))),
     "med": median, "dis": dispersion, "ave": average,
     "len": lambda *args: len(args), "max": lambda *args: max(*args), "min": lambda *args: min(*args),
     "abs": abs, "sum": lambda *args: sum(args), "gm": geometric_mean}


def eval(string: str):
    return builtins.eval(string, {"__builtins__": functions})


def calculator(string: str) -> Union[int, float]:
    string = string.lower()
    result = round(eval(string), 5)
    if result == int(result):
        return int(result)
    return result


def main(string: str) -> Union[str, None]:
    try:
        return f"{string}={calculator(string)}"
    except:
        return None
