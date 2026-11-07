import base64, collections, colorsys, copy, dataclasses, datetime, enum, functools  # noqa
import hashlib, heapq, importlib.machinery, io, itertools, json, math, pathlib, queue, random, re, runpy, shutil  # noqa
import socket, ssl, string, struct, subprocess, sys, tempfile, textwrap, threading, time  # noqa
import traceback, typing, urllib.parse, urllib.request, zlib  # noqa
import pygame  # noqa
import numpy  # noqa
import pygame.surfarray  # noqa
try:
    import certifi  # noqa
except ImportError:
    pass
try:
    import numba  # noqa  (fast gas kernels, the game falls back to numpy without it)
except Exception:
    pass
import launcher

if __name__ == '__main__':
    launcher.main()
