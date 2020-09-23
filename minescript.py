import logging
import os
import pprint
import shutil

from antlr4 import CommonTokenStream, FileStream

from MineScriptLexer import MineScriptLexer
from MineScriptParser import MineScriptParser
from Visitor import Visitor
from MappingVisitor import MappingVisitor

logging.basicConfig(level=logging.INFO, format="%(message)s")

packmeta = """{
  "pack": {
    "pack_format": 1,
    "description": "%s"
  }
}
"""

load_file = """{
    "values": [
        "%s:load"
    ]
}"""

tick_file = """{
    "values": [
        "%s:tick"
    ]
}"""

def parent(path):
    return os.path.abspath(os.path.join(path, os.pardir))

def mkdir(*args):
    try:
        os.mkdir(*args)
    except FileExistsError:
        pass

def create_structure(name, description, path):
    try:
        os.mkdir(os.path.join(path, name))
    except FileExistsError:
        shutil.rmtree(os.path.join(path, name))
        os.mkdir(os.path.join(path, name))
        
    mkdir(os.path.join(path, name, "data"))
    with open(os.path.join(path, name, "pack.mcmeta"), "w") as file:
        file.write(packmeta%description)
    mkdir(os.path.join(path, name, "data", "minecraft"))
    mkdir(os.path.join(path, name, "data", name))
    mkdir(os.path.join(path, name, "data", "minecraft", "tags"))
    mkdir(os.path.join(path, name, "data", "minecraft", "tags", "functions"))
    mkdir(os.path.join(path, name, "data", name, "functions"))
    mkdir(os.path.join(path, name, "data", name, "tags"))
    with open(os.path.join(path, name, "data", "minecraft", "tags", "functions", "load.json"), "w") as file:
        file.write(load_file%name)
    with open(os.path.join(path, name, "data", "minecraft", "tags", "functions", "tick.json"), "w") as file:
        file.write(tick_file%name)
        
def assemble_pack(name, visitor, path):
    commands = 0
    added = set()
    with open(os.path.join(path, name, "data", name, "functions", "_setup.mcfunction"), "w") as usrvar:
        with open(os.path.join(path, name, "data", name, "functions", "_vars.mcfunction"), "w") as tempvar:
            for variable in visitor.igmemory:
                if variable.startswith("_"):
                    file = tempvar
                else:
                    file = usrvar
                if not visitor.igmemory[variable].endswith("[]") or variable.startswith("_"):
                    file.write(f"scoreboard objectives add {variable} dummy \"{variable}\"\n")
                    commands += 1
                    
            for func in visitor.local:
                for variable in visitor.local[func]:
                    if variable not in added:
                        if variable.startswith("_"):
                            file = tempvar
                        else:
                            file = usrvar
                        if not visitor.local[func][variable].endswith("[]") or variable.startswith("_"):
                            file.write(f"scoreboard objectives add {variable}+local dummy \"{variable}\"\n")
                            commands += 1
                        added.add(variable)
                
    for loop in visitor.igloops:
        with open(os.path.join(path, name, "data", name, "functions", f"{loop}.mcfunction"), "w") as file:
            for command in visitor.igloops[loop]:
                file.write(command + "\n")
                commands += 1
                
    for function in visitor.igfunctions:
        with open(os.path.join(path, name, "data", name, "functions", f"{function}.mcfunction"), "w") as file:
            if function == "load":
                file.write(f"function {name}:_setup\n")
                file.write(f"function {name}:_vars\n")
                commands += 2
            for command in visitor.igfunctions[function]["code"]:
                file.write(command + "\n")
                commands += 1
    if "load" not in visitor.igfunctions:
        with open(os.path.join(path, name, "data", name, "functions", "load.mcfunction"), "w") as file:
            file.write(f"function {name}:_setup\n")
            file.write(f"function {name}:_vars\n")
            commands += 2
    print(commands)

def get_tree(file):
    inp = FileStream(file)
    lexer = MineScriptLexer(inp)
    stream = CommonTokenStream(lexer)
    parser = MineScriptParser(stream)
    tree = parser.prog()
    return tree
    
def visit(name, file):
    tree = get_tree(file)
    mapvisitor = MappingVisitor(name, file)
    try:
        mapvisitor.visit(tree)
    except Exception:
        return None
    visitor = Visitor(name, file)
    visitor.igfunctions = mapvisitor.igfunctions
    visitor.igmemory = mapvisitor.igmemory
    visitor.visit(tree)
    print(visitor.tempvars)
    return visitor

def main(name, file):
    path = parent(file)
    
    path = os.path.join(path, "build")
    mkdir(path)
    
    distpath = os.path.join(parent(file), "dist")
    mkdir(distpath)

    create_structure(name, "Generated using MineScript 2.0", path)
    visitor = visit(name, file)
    
    assemble_pack(name, visitor, path)
    shutil.make_archive(os.path.join(distpath, name), 'zip', os.path.join(path, name))

if __name__ == "__main__":
    # file = "test.txt"
    # v = visit("test", file)
    # if v is not None:
    #     print(v.igmemory)
    #     print(v.tempvars)
    #     pprint.pprint(v.igfunctions)
    #     pprint.pprint(v.igloops)
    main("test", "test.txt")
