import ast
import sys


def strip(src):
    tree = ast.parse(src)
    for node in ast.walk(tree):
        if isinstance(node, (ast.Module, ast.FunctionDef, ast.AsyncFunctionDef, ast.ClassDef)):
            b = node.body
            if b and isinstance(b[0], ast.Expr) and isinstance(getattr(b[0], 'value', None), ast.Constant) \
                    and isinstance(b[0].value.value, str):
                node.body = b[1:] or [ast.Pass()]
    return ast.unparse(ast.fix_missing_locations(tree)) + '\n'


if __name__ == '__main__':
    with open(sys.argv[1], encoding='utf-8') as f:
        out = strip(f.read())
    with open(sys.argv[2], 'w', encoding='utf-8') as f:
        f.write(out)
