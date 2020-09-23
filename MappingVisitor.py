from logs import Logger
from MineScriptParser import MineScriptParser
from MineScriptVisitor import MineScriptVisitor

class MappingVisitor(MineScriptVisitor):
    def __init__(self, name, filename):
        self.logger = Logger(filename)
        self.igfunctions = {}
        self.igmemory = {}
        self.igfunc = None
        
    def visitFunctionDeclaration(self, ctx):
        type_ = ctx.type_.text
        name = ctx.WORD().getText()
        
        if self.igfunc is not None:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Nested functions not supported ('{name}' inside '{self.igfunc}')", line, char, "error")
            raise Exception()
        
        if name in self.igfunctions:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Multiple definitions of function '{name}'", line, char, "error")
            raise Exception()
        
        self.igfunctions[name] = {
            "code" : [],
            "args": []
        }
        if type_ != "void": 
            self.igmemory[f"_f_{name}"] = type_
            self.igfunctions[name]["return"] = f"_f_{name}"
        
        for functionArg in ctx.functionArg():
            arg_type = functionArg.type_.text
            arg_name = functionArg.WORD().getText()
            self.igfunctions[name]["args"].append((arg_name, arg_type))
            
        if (name == "load" or name == "tick") and len(self.igfunctions[name]["args"]) != 0:
            line = ctx.functionArg(0).start.line
            char = ctx.functionArg(0).start.column
            self.logger.log(f"The built-in function '{name}' takes no args", line, char, "error")
            raise Exception()

        self.igfunc = name
        self.visitChildren(ctx)            
        self.igfunc = None        