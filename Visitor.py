import sys

import antlr4

from exceptions import CompileTimeException
from logs import Logger
from MineScriptParser import MineScriptParser
from MineScriptVisitor import MineScriptVisitor

CONTROL_FLOW_CONTEXTS = [MineScriptParser.IfStatementContext,
                         MineScriptParser.ForStatementContext,
                         MineScriptParser.WhileStatementContext]

class Literal:
    def __init__(self, value, type, const=False):
        self.value = value
        self.type = type
        self.const = const

class Visitor(MineScriptVisitor):
    def __init__(self, name, filename):
        self.logger = Logger(filename)
        self.name = name
        
        self.memory = {}
        self.localmemory = {}
        self.functionargs = {}
        self.func = None
        self.r_value = None
        
        self.igmemory = {}
        self.local = {}
        self.igfunctions = {}
        self.igfunc = None
        self.igfuncinfo = None
        
        self.igloops = {}
        
        self.usedvars = set()
        self.tempvars = set()
        self.prefixes = []
        self.loop = []
        self.break_var = []
        self.loops = 0
        self.tags = 0
        
    def get_value(self, obj):
        if isinstance(obj, Literal):
            if obj.type == "char[]":
                print(obj.value)
                return ''.join(obj.value)
            if obj.type == "char":
                return chr(obj.value)
            return obj.value
        else:
            return self.get_value(self.memory[obj])
        
    def at_compile_time(self, obj):
        if isinstance(obj, Literal):
            return True
        if obj.startswith("$"):
            return True
        return False
        
    def is_used(self, ctx):
        aux = ctx.parentCtx
        while aux is not None and not isinstance(aux, MineScriptParser.StatContext):
            if not isinstance(aux, MineScriptParser.IgnoreContext):
                return True
            aux = aux.parentCtx
        return False
    
    def is_used_on_condition(self, ctx):
        aux = ctx.parentCtx
        while aux is not None and not isinstance(aux, MineScriptParser.StatContext):
            for context in CONTROL_FLOW_CONTEXTS:
                if isinstance(aux, context):
                    return True
            aux = aux.parentCtx
        return False
    
    def is_defined(self, name):
        if name.startswith("$"):
            return name in self.memory
        if self.igfunc is None:
            return name in self.igmemory
        else:
            name = name.replace("+local", "")
            if name in self.local[self.igfunc]:
                return True
            return name in self.igmemory
        
    def assert_is_defined(self, name, ctx):
        if not self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
            raise CompileTimeException()
    
    def get_type(self, name):
        if isinstance(name, Literal):
            return name.type
        else:                
            name = name.replace("+local", "")
            if name.startswith("$"):
                return self.memory[name].type
            if self.igfunc is None:
                return self.igmemory[name]
            else:
                if name in self.local[self.igfunc]:
                    return self.local[self.igfunc][name]
                else:
                    return self.igmemory[name]
        
    def assert_types_match(self, correct, given, ctx):
        if self.get_type(correct) != self.get_type(given):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Mismatching types: '{self.get_type(correct)}' and '{self.get_type(given)}'", line, char, "error")
            raise CompileTimeException()
                
    def add_var(self, name, type_, ctx=None):
        if name.startswith("$"):
            self.memory[name] = Literal(None, type_)
        else:
            if self.igfunc is None or name.startswith("_"):
                if name not in self.igmemory or ctx is None:
                    self.igmemory[name] = type_
                else:
                    line = ctx.start.line
                    char = ctx.start.column
                    self.logger.log(f"Multiple definitions of variable '{name}'", line, char, "error")
                    raise CompileTimeException()
            else:
                if name not in self.local[self.igfunc] or ctx is None:
                    self.local[self.igfunc][name] = type_
                else:
                    line = ctx.start.line
                    char = ctx.start.column
                    self.logger.log(f"Multiple definitions of variable '{name}'", line, char, "error")
                    raise CompileTimeException()
            
    def set_var(self, name, value, ctx):
        if isinstance(value, Literal):
            if not name.startswith("$"):
                if not self.get_type(value).endswith("[]"):
                    self.add_cmd(f"scoreboard players set #MineScript {name} {value.value}", ctx)
                else:
                    list_value = ""
                    for item in value.value:
                        if self.get_type(value) == "char[]":
                            list_value += f'{ord(item)},'
                        elif self.get_type(value) == "int[]":
                            list_value += str(item.value) + ","
                    list_value = "{value:" + f"[{list_value[:-1]}]," + f"size:{str(len(value.value))}"+ "}"
                    self.add_cmd(f"data modify storage {self.name}:minescript {name} set value {list_value}", ctx)
            else:
                self.memory[name] = value
        else:
            if name.startswith("$"):
                line = ctx.start.line
                char = ctx.start.column
                self.logger.log("Compile-time variable can't be assigned to an in-game variable", line, char, "error")
                raise CompileTimeException()
            if not self.get_type(value).endswith("[]"):
                self.add_cmd(f"scoreboard players operation #MineScript {name} = #MineScript {value}", ctx)
            else:
                self.add_cmd(f"data modify storage {self.name}:minescript {name} set from storage {self.name}:minescript {value}", ctx)
                
    def get_arr_element(self, name, element, ctx):
        if self.get_type(element) != "int":
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"List indexes must be intergers (was {self.get_type(element)})", line, char, "error")
            raise CompileTimeException()
        if not name.startswith("$"):
            if isinstance(element, Literal):
                temp_result = self.get_temp_var(self.get_type(name)[:-2])
                self.add_cmd(f"execute store result score #MineScript {temp_result} run "
                            f"data get storage {self.name}:minescript {name}.value[{element.value}]", ctx)
                return temp_result
            else:
                temp_list = self.get_temp_var(self.get_type(name))
                count = self.get_temp_var("int")
                #size = self.get_temp_var("int")
                temp_result = self.get_temp_var(self.get_type(name)[:-2])
                #self.add_cmd(f"execute store result score #MineScript {size} run "
                #             f"data get storage {self.name}:minescript {name}.size", ctx)
                self.set_var(count, Literal(0, "int"), ctx)
                self.set_var(temp_list, name, ctx)
                name = f"_loop{self.loops}"
                self.add_cmd(f"function {self.name}:{name}", ctx)
                
                self.start_loop(name, None)
                self.add_cmd(f"scoreboard players add #MineScript {count} 1", ctx)
                self.add_cmd(f"execute store result score #MineScript {temp_result} run "
                            f"data get storage {self.name}:minescript {temp_list}.value[0]", ctx)
                self.add_cmd(f"data remove storage {self.name}:minescript {temp_list}.value[0]", ctx)
                self.add_cmd(f"execute unless score #MineScript {count} > #MineScript {element} run "
                            f"function {self.name}:{name}", ctx)
                self.end_loop()
                
                self.mark_unused(temp_list)
                self.mark_unused(count)
                #self.mark_unused(size)
                
                return temp_result
        else:
            if isinstance(element, Literal):
                return self.memory[name][element.value]
            elif element.startswith("$"):
                return self.memory[name][self.memory[element].value]
        
    def set_arr_element(self, name, element, value, ctx):
        if self.get_type(element) != "int":
                line = ctx.start.line
                char = ctx.start.column
                self.logger.log(f"List indexes must be intergers (was {self.get_type(element)})", line, char, "error")
                raise CompileTimeException()
        if not name.startswith("$"):
            if isinstance(element, Literal):
                if isinstance(value, Literal):
                    self.add_cmd(f"data modify storage {self.name}:minescript {name}.value[{element.value}] value {value.value}", ctx)
                else:
                    self.add_cmd(f"execute store result storage {self.name}:minescript {name}.value[{element.value}] run "
                                f"scoreboard objectives get #MineScript {value}", ctx)
            else:
                temp_list = self.get_temp_var(self.get_type(name))
                count = self.get_temp_var("int")
                done = self.get_temp_var("int")
                size = self.get_temp_var("int")
                self.add_cmd(f"execute store result score #MineScript {size} run "
                            f"data get storage {self.name}:minescript {name}.size", ctx)
                self.set_var(count, Literal(0, "int"), ctx)
                self.set_var(done, Literal(0, "int"), ctx)
                self.set_var(temp_list, Literal([], self.get_type(name)), ctx)
                lname = f"_loop{self.loops}"
                self.add_cmd(f"function {self.name}:{lname}", ctx)
                
                self.start_loop(lname, None)
                self.add_cmd(f"execute unless score #MineScript {count} = #MineScript {element} run "
                            f"data modify storage {self.name}:minescript {temp_list}.value append from storage "
                            f"{self.name}:minescript {name}.value[0]", ctx)
                if isinstance(value, Literal):
                    self.add_cmd(f"execute if score #MineScript {count} = #MineScript {element} "
                                f"if score #MineScript {done} matches 0 run "
                                f"data modify storage {self.name}:minescript {temp_list}.value append "
                                f"value {value.value}", ctx)
                else:
                    self.add_cmd(f"execute if score #MineScript {count} = #MineScript {element} "
                                f"if score #MineScript {done} matches 0 run "
                                f"data modify storage {self.name}:minescript {temp_list}.value append value 0", ctx)
                    self.add_cmd(f"execute if score #MineScript {count} = #MineScript {element} "
                                f"if score #MineScript {done} matches 0 run "
                                f"execute store result storage {self.name}:minescript {temp_list}.value[-1] int 1 run "
                                f"scoreboard players get #MineScript {value}", ctx)
                self.add_cmd(f"execute if score #MineScript {count} = #MineScript {element} "
                            f"if score #MineScript {done} matches 0 run "
                            f"scoreboard players set #MineScript {done} 1", ctx)
                self.add_cmd(f"data remove storage {self.name}:minescript {name}.value[0]", ctx)
                self.add_cmd(f"scoreboard players add #MineScript {count} 1", ctx)
                self.add_cmd(f"execute unless score #MineScript {count} >= #MineScript {size} run "
                            f"function {self.name}:{lname}", ctx)
                self.end_loop()

                self.add_cmd(f"data modify storage {self.name}:minescript {name}.value set from " 
                            f"storage {self.name}:minescript {temp_list}.value", ctx)
                self.mark_unused(temp_list)
                self.mark_unused(count)
                self.mark_unused(size)
                self.mark_unused(done)
                if isinstance(value, str):
                    self.mark_unused(value)
        else:
            if self.at_compile_time(value):
                if self.at_compile_time(element):
                    self.memory[name].value[self.get_value(element)] = self.get_value(value)
                else:
                    line = ctx.start.line
                    char = ctx.start.column
                    self.logger.log(f"List index must be evaluated at compile-time", line, char, "error")
                    raise CompileTimeException()
            else:
                line = ctx.start.line
                char = ctx.start.column
                self.logger.log(f"Assigned value must be evaluated at compile-time", line, char, "error")
                raise CompileTimeException()
                
            
    def get_temp_var(self, type_):
        n = None
        for i in range(len(self.tempvars)):
            if f"_var{i}" not in self.tempvars:
                n = i
                break
        if n is None: n = len(self.tempvars)
        name = f"_var{n}"
        self.add_var(name, type_)
        self.tempvars.add(name)
        self.usedvars.add(name)
        return name
    
    def mark_unused(self, name):
        if name.startswith("_var") and name in self.tempvars:
            self.tempvars.remove(name)
    
    def add_cmd(self, command, ctx):
        if len(self.prefixes) != 0:
            command = "execute " + " ".join(self.prefixes) + " run " + command
        if self.loop != []:
            self.igloops[self.loop[-1]].append(command)
        elif self.igfunc is not None:
            self.igfunctions[self.igfunc]["code"].append(command)
        else:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log("All code must reside inside a function", line, char, "error")
            raise CompileTimeException()
            
    def start_loop(self, name, break_var):
        self.igloops[name] = []
        self.loop.append(name)
        self.break_var.append(break_var)
        if break_var is not None:
            self.prefixes.append(f"unless score #MineScript {break_var} matches 0")
        self.loops += 1
        
    def end_loop(self):
        self.loop.pop(-1)
        bv = self.break_var.pop(-1)
        if bv is not None:
            self.prefixes.pop(-1)
            self.mark_unused(bv)        
            
    def compare(self, expr1, expr2, op, ctx):
        self.assert_types_match(expr1, expr2, ctx)
        if self.at_compile_time(expr1) and self.at_compile_time(expr2):
            return Literal(eval(f"self.get_value(expr1){op}self.get_value(expr2)"), "int")
        elif isinstance(expr1, str) and self.at_compile_time(expr2):
            temp_result = self.get_temp_var("int")
            self.set_var(temp_result, Literal(0, "int"), ctx)
            if op == "==":
                self.add_cmd(f"execute if score #MineScript {expr1} matches {self.get_value(expr2)} run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == "<=":
                self.add_cmd(f"execute if score #MineScript {expr1} matches ..{self.get_value(expr2)} run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == ">=":
                self.add_cmd(f"execute if score #MineScript {expr1} matches {self.get_value(expr2)}.. run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == "<":
                self.add_cmd(f"execute unless score #MineScript {expr1} matches {self.get_value(expr2)}.. run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == ">":
                self.add_cmd(f"execute unless score #MineScript {expr1} matches ..{self.get_value(expr2)} run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == "!=":
                self.add_cmd(f"execute if score #MineScript {expr1} matches {self.get_value(expr2)} run scoreboard players set #MineScript {temp_result} 1", ctx)
            self.mark_unused(expr1)
            return temp_result
                        
        elif isinstance(expr2, str) and self.at_compile_time(expr1):
            if op == "==" or op == "!=": newop = op
            elif op == ">=": newop = "<="
            elif op == "<=": newop = ">="
            elif op == ">": newop = "<"
            elif op =="<": newop = ">"
            return self.compare(expr2, expr1, newop, ctx)
        
        elif isinstance(expr1, str) and isinstance(expr2, str):
            temp_result = self.get_temp_var("int")
            self.set_var(temp_result, Literal(0, "int"), ctx)
            if op != "==" and op != "!=":
                self.add_cmd(f"execute if score #MineScript {expr1} {op} #MineScript {expr2} run scoreboard players set #MineScript {temp_result} 1", ctx)
            elif op == "==":
                self.add_cmd(f"execute if score #MineScript {expr1} = #MineScript {expr2} run scoreboard players set #MineScript {temp_result} 1", ctx)
            else:
                self.add_cmd(f"execute unless score #MineScript {expr1} = #MineScript {expr2} run scoreboard players set #MineScript {temp_result} 1", ctx)
            self.mark_unused(expr1)
            self.mark_unused(expr2)
            return temp_result
    
    def operate(self, expr1, expr2, op, ctx):
        self.assert_types_match(expr1, expr2, ctx)
        
        if self.at_compile_time(expr1) and self.at_compile_time(expr2):
            return Literal(eval(f"self.get_value(expr1){op}self.get_value(expr2)"), self.get_type(expr1))
        
        elif isinstance(expr1, str) and self.at_compile_time(expr2):
            temp_result = self.get_temp_var(self.get_type(expr2))
            if op == "+":
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players add #MineScript {temp_result} {self.get_value(expr2)}", ctx)
            elif op == "-":
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players remove #MineScript {temp_result} {self.get_value(expr2)}", ctx)
            elif op == "*":
                self.set_var(temp_result, expr2, ctx)
                self.add_cmd(f"scoreboard players operation #MineScript {temp_result} *= #MineScript {expr1}", ctx)
            elif op == "/":
                temp_var = self.get_temp_var(self.get_type(expr2))
                self.set_var(temp_var, expr2, ctx)
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players operation #MineScript {temp_result} /= #MineScript {temp_var}", ctx)
                self.mark_unused(temp_var)
            elif op == "%":
                temp_var = self.get_temp_var(self.get_type(expr2))
                self.set_var(temp_var, expr2, ctx)
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players operation #MineScript {temp_result} %= #MineScript {temp_var}", ctx)
                self.mark_unused(temp_var)
            self.mark_unused(expr1)
            return temp_result
                        
        elif isinstance(expr2, str) and self.at_compile_time(expr1):
            if op == "+" or op == "*":
                return self.operate(expr2, expr1, op, ctx)
            else:
                temp_result = self.get_temp_var(self.get_type(expr1))
                if op == "-":
                    self.set_var(temp_result, expr1, ctx)
                    self.add_cmd(f"scoreboard players operation #MineScript {temp_result} -= #MineScript {expr2}", ctx)
                elif op == "/":
                    temp_var = self.get_temp_var(self.get_type(expr1))
                    self.set_var(temp_var, expr1, ctx)
                    self.set_var(temp_result, expr2, ctx)
                    self.add_cmd(f"scoreboard players operation #MineScript {temp_result} /= #MineScript {temp_var}", ctx)
                    self.mark_unused(temp_var)
                elif op == "%":
                    temp_var = self.get_temp_var(self.get_type(expr1))
                    self.set_var(temp_var, expr1, ctx)
                    self.set_var(temp_result, expr2, ctx)
                    self.add_cmd(f"scoreboard players operation #MineScript {temp_result} %= #MineScript {temp_var}", ctx)
                    self.mark_unused(temp_var)
                self.mark_unused(expr2)
                return temp_result
        
        elif isinstance(expr1, str) and isinstance(expr2, str):
            temp_result = self.get_temp_var(self.get_type(expr1))
            self.set_var(temp_result, expr1, ctx)
            self.add_cmd(f"scoreboard players operation #MineScript {temp_result} {op}= #MineScript {expr2}", ctx)
            self.mark_unused(expr1)
            self.mark_unused(expr2)
            return temp_result
        
    def visitParentheses(self, ctx):
        return self.visit(ctx.expr())
            
    def visitVariableDeclaration(self, ctx):
        type_ = ctx.type_.text
        declarations = ctx.variableAssignement()
        for dec in declarations:
            name = dec.WORD().getText()
            
            suffix = "" if self.igfunc is None or dec.PREFIX() is not None else "+local" 
            if dec.PREFIX() is not None: name = "$"+name
            
            self.add_var(name, type_ if dec.arr() is None else type_+"[]", ctx)
            l = dec.expr()
            if l is not None:
                value = self.visit(l)
                self.assert_types_match(value, name, l)
                self.set_var(name+suffix, value, ctx)
                if isinstance(value, str):
                    self.mark_unused(value)                
                    
    def visitVariableAssignement(self, ctx):
        name = ctx.WORD().getText()
        if ctx.PREFIX() is not None: name = "$"+name
        self.assert_is_defined(name, ctx)

        suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
        if ctx.expr() is not None:
            value = self.visit(ctx.expr())
            if ctx.arr() is None:
                self.assert_types_match(name, value, ctx)
                self.set_var(name+suffix, value, ctx)
            else:
                element = self.visit(ctx.arr().expr())
                if not name.startswith("$"):
                    self.igmemory["_temp"] = self.get_type(name)[:-2]
                    self.assert_types_match("_temp", element, ctx)
                    self.set_arr_element(name+suffix, element, value, ctx)
                    del self.igmemory["_temp"]
                    if isinstance(element, str):
                        self.mark_unused(element)
                else:
                    self.assert_types_match(Literal(0, "int"), element, ctx)
                    self.set_arr_element(name, element, value, ctx)
                    
            if isinstance(value, str):
                self.mark_unused(value)
            
        if not name.startswith("$"):
            if ctx.arr() is not None and self.is_used(ctx):
                return self.get_arr_element(name+suffix, self.visit(ctx.arr().expr()), ctx)
            elif ctx.arr() is None and self.is_used_on_condition(ctx):
                temp_result = self.get_temp_var(self.get_type(name))
                self.set_var(temp_result, name+suffix, ctx)
                return temp_result
            else:
                return name+suffix
        else:
            return name
            
    def visitArray(self, ctx):
        arr = []
        arr_type = None
        for expr in ctx.expr():
            value = self.visit(expr)
            if arr_type is None:
                arr_type = value
            else:
                self.assert_types_match(arr_type, value, expr)
            arr.append(value)
        if self.is_used(ctx):
            temp_result = self.get_temp_var(self.get_type(arr_type) + "[]")
            self.set_var(temp_result, Literal(arr, self.get_type(arr_type) + "[]"), ctx)
            return temp_result
                    
    def visitFunctionDeclaration(self, ctx):
        name = ctx.WORD().getText()
        self.igfunc = name
        self.local[self.igfunc] = {}
        
        for arg in self.igfunctions[name]["args"]:
            self.add_var(arg[0], arg[1])
        
        self.add_var(f"_break_{name}", "int")
        self.igfuncinfo = {"break": f"_break_{name}"}
        self.set_var(f"_break_{name}", Literal(0, "int"), ctx)
        
        self.prefixes.append(f"unless score #MineScript {self.igfuncinfo['break']} matches 1")
        self.visit(ctx.stat())
        self.prefixes.pop(-1)
        self.igfuncinfo = None
        self.igfunc = None
        
    def visitFunctionCall(self, ctx):
        name = ctx.WORD().getText()
        if name not in self.igfunctions:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undefined function '{name}'", line, char, "error")
            raise CompileTimeException()
        else:
            args = []
            for expr in ctx.expr():
                args.append((self.visit(expr), expr.start.line, expr.start.column))
            fargs = self.igfunctions[name]["args"]
            if len(args) != len(fargs):
                line = ctx.start.line
                char = ctx.stop.column
                msg = (f"Function '{name}' takes {len(fargs)} arguments, "
                       f"but {len(args)} {'was' if len(args) == 1 else 'were'} given")
                self.logger.log(msg, line, char, "error")
                raise CompileTimeException()
            else:
                for i in range(len(args)):
                    if not self.get_type(args[i][0]) == fargs[i][1]:
                        msg = (f"Argument '{fargs[i][0]}' is of type '{fargs[i][1]}', "
                                f"but '{self.get_type(args[i][0])}' was provided.")
                        self.logger.log(msg, args[i][1], args[i][2], "error")
                        raise CompileTimeException()
                    else:
                        self.set_var(fargs[i][0]+"+local", args[i][0], ctx)
                self.add_cmd(f"function {self.name}:{name}", ctx)

            if "return" in self.igfunctions[name]:
                return self.igfunctions[name]["return"]
            
    def visitReturnStatement(self, ctx):
        if self.igfunc is None:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log("Return outside function", line, char, "error")
            raise CompileTimeException()
        else:
            if "return" in self.igfunctions[self.igfunc]:
                if ctx.expr() is None:
                    line = ctx.stop.line
                    char = ctx.stop.column
                    self.logger.log("No return value for non-void function", line, char, "error")
                    raise CompileTimeException()
                else:
                    value = self.visit(ctx.expr())
                    self.assert_types_match(self.igfunctions[self.igfunc]["return"], value, ctx.expr())
 
                    self.set_var(self.igfunctions[self.igfunc]["return"], value, ctx)
                    self.add_cmd(f"scoreboard players set #MineScript {self.igfuncinfo['break']} 1", ctx)
                    
                    if isinstance(value, str):
                        self.mark_unused(value)
            else:
                if ctx.expr() is not None:
                    line = ctx.stop.line
                    char = ctx.stop.column
                    self.logger.log("Void function returns a value", line, char, "error")
                    raise CompileTimeException()
                else:
                    self.add_cmd(f"scoreboard players set #MineScript {self.igfuncinfo['break']} 1", ctx)
                    
    def visitLiteral(self, ctx):
        if ctx.CHAR() is not None:
            return Literal(eval(f"ord({ctx.CHAR().getText()})"), "char")
        elif ctx.NUMBER() is not None:
            return Literal(int(ctx.NUMBER().getText()), "int")
        elif ctx.STRING() is not None:
            return Literal(list(ctx.STRING().getText()[1:-1]), "char[]")
        
    def visitVariableIncrementPos(self, ctx):
        name = ctx.WORD().getText()
        if ctx.PREFIX(): name = "$"+name
        self.assert_is_defined(name, ctx)

        suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
        used = self.is_used(ctx)
        if used: 
            temp_result = self.get_temp_var(self.get_type(name))
            self.set_var(temp_result, name+suffix, ctx)
        self.add_cmd(f"scoreboard players add #MineScript {name}{suffix} 1", ctx)
        if used:
            return temp_result
        
    def visitVariableIncrementPre(self, ctx):
        name = ctx.WORD().getText()
        if ctx.PREFIX(): name = "$"+name
        self.assert_is_defined(name, ctx)
        
        suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
        self.add_cmd(f"scoreboard players add #MineScript {name}{suffix} 1", ctx)
        return name+suffix
        
    def visitVariableDecrementPos(self, ctx):
        name = ctx.WORD().getText()
        if ctx.PREFIX(): name = "$"+name
        self.assert_is_defined(name, ctx)
        
        suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
        used = self.is_used(ctx)
        if used: 
            temp_result = self.get_temp_var(self.get_type(name))
            self.set_var(temp_result, name+suffix, ctx)
        self.add_cmd(f"scoreboard players remove #MineScript {name}{suffix} 1", ctx)
        if used:
            return temp_result
        
    def visitVariableDecrementPre(self, ctx):
        name = ctx.WORD().getText()
        if ctx.PREFIX(): name = "$"+name
        self.assert_is_defined(name, ctx)
        
        suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
        self.add_cmd(f"scoreboard players remove #MineScript {name}{suffix} 1", ctx)
        return name
            
    def visitVariableComparison(self, ctx):
        expr1, expr2 = ctx.expr()
        expr1 = self.visit(expr1)
        expr2 = self.visit(expr2)
        if self.is_used(ctx):
            return self.compare(expr1, expr2, ctx.type_.text, ctx)
        
    def visitVariableOperation(self, ctx):
        expr1, expr2 = ctx.expr()
        expr1 = self.visit(expr1)
        expr2 = self.visit(expr2)
        if self.is_used(ctx):
            return self.operate(expr1, expr2, ctx.type_.text, ctx)
            
    def visitIfStatement(self, ctx):
        condition = self.visit(ctx.expr())
        if isinstance(condition, str):
            self.prefixes.append(f"if score #MineScript {condition} matches 1")
            self.visit(ctx.stat(0))
            self.prefixes.pop(-1)
            if len(ctx.stat()) > 1:
                self.prefixes.append(f"unless score #MineScript {condition} matches 1")
                self.visit(ctx.stat(1))
                self.prefixes.pop(-1)
            self.mark_unused(condition)
        else:
            if condition.value:
                self.visit(ctx.stat(0))
            elif len(ctx.stat()) > 1:
                self.visit(ctx.stat(1))

    def visitForStatement(self, ctx):
        if len(ctx.expr()) == 3:
            init, condition, update = ctx.expr()
        else:
            init = ctx.variableDeclaration()
            condition, update = ctx.expr()
        init_value = self.visit(init)
        name = f"_loop{self.loops}"
        condition_value = self.visit(condition)
        
        break_var = self.get_temp_var("int")
        self.set_var(break_var, Literal(1, "int"), ctx)
        
        always_true = False
        if isinstance(condition_value, str):
            self.add_cmd(f"execute unless score #MineScript {condition_value} matches 0 run function {self.name}:{name}", ctx)
        elif isinstance(condition_value, Literal):
            if not condition_value.value:
                line = condition.start.line
                char = condition.start.column
                self.logger.log("Condition is always false", line, char, "warning")
                self.mark_unused(break_var)
                return
            line = condition.start.line
            char = condition.start.column
            self.logger.log("Condition is always true", line, char, "warning")
            self.add_cmd(f"function {self.name}:{name}", ctx)
            always_true = True
            
        self.start_loop(name, break_var)
        self.visit(ctx.stat())
        update_value = self.visit(update)
        if always_true:
            self.add_cmd(f"function {self.name}:{name}", ctx)
        else:
            if isinstance(condition_value, str):
                self.mark_unused(condition_value)
            condition_value = self.visit(condition)
            self.add_cmd(f"execute unless score #MineScript {condition_value} matches 0 run function {self.name}:{name}", ctx)
        self.end_loop()
        
        if isinstance(init_value, str):
            self.mark_unused(init_value)
        if isinstance(condition_value, str):
            self.mark_unused(condition_value)
        if isinstance(update_value, str):
            self.mark_unused(update_value)
        
    def visitWhileStatement(self, ctx):
        condition = ctx.expr()
        condition_value = self.visit(condition)
        name = f"_loop{self.loops}"
        
        break_var = self.get_temp_var("int")
        self.set_var(break_var, Literal(1, "int"), ctx)
        
        always_true = False
        if isinstance(condition_value, Literal):
            if condition_value.value:
                self.add_cmd(f"function {self.name}:{name}", ctx)
                always_true = True
            else:
                line = condition.start.line
                char = condition.start.column
                self.logger.log("Condition is always false", line, char, "warning")
                return
        else:
            self.add_cmd(f"execute unless score #MineScript {condition_value} matches 0 run function {self.name}:{name}", ctx)
        
        self.start_loop(name, break_var)
        self.visit(ctx.stat())
        if always_true:
            self.add_cmd(f"function {self.name}:{name}", ctx)
        else:
            if isinstance(condition_value, str):
                self.mark_unused(condition_value)
            condition_value = self.visit(condition)
            self.add_cmd(f"execute unless score #MineScript {condition_value} matches 0 run function {self.name}:{name}", ctx)
        self.end_loop()
        
        if isinstance(condition_value, str):
            self.mark_unused(condition_value)
            
    def visitBreakStatement(self, ctx):
        if len(self.loop) == 0:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log("Break statement is outside of a loop", line, char, "error")
            raise CompileTimeException()

        self.set_var(self.break_var[-1], Literal(0, "int"), ctx)
        
    def visitPrintStatement(self, ctx):
        if len(ctx.expr()) < 3:
            line = ctx.start.line
            char = ctx.stop.column
            msg = (f"Built-in function 'print' takes at least 3 arguments, "
                   f"but only {len(ctx.expr())} {'was' if len(ctx.expr()) == 1 else 'were'} given")
            self.logger.log(msg, line, char, "error")
            raise CompileTimeException()
        selector, color, *args = ctx.expr()
        selector_value = self.visit(selector)
        color_value = self.visit(color)
        if self.at_compile_time(selector_value) and self.get_type(selector_value) == "char[]":
            if self.at_compile_time(color_value) and self.get_type(color_value) == "char[]":
                pass
            else:
                line = color.start.line
                char = color.stop.column
                self.logger.log("The second argument of 'print' must be a string "
                                "evaluated at compile time.", line, char, "error")
                raise CompileTimeException()
        else:
            line = selector.start.line
            char = selector.stop.column
            self.logger.log("The first argument of 'print' must be a string "
                            "evaluated at compile time.", line, char, "error")
            raise CompileTimeException()
        
        color_text = f"\"color\":\"{self.get_value(color_value)}\""
        command = ""
        for arg in args:
            arg_value = self.visit(arg)
            if self.at_compile_time(arg_value):
                command += ',{"text":'
                if self.get_type(arg_value) == "char":
                    command += f'"{chr(self.get_value(arg_value))}"'
                else:
                    command += f'"{str(self.get_value(arg_value))}"'
                command += ", " + color_text + "}"
            else:
                if self.get_type(arg_value) == "int":
                    command += ',{"score":{"name":"#MineScript","objective":"'+arg_value+'"}}'
                self.mark_unused(arg_value)
        self.add_cmd(f"tellraw {selector_value.value} [{command[1:]}]", ctx)
        
    def visitMcCommand(self, ctx):
        pass
        
    def visitCast(self, ctx):
        expr = self.visit(ctx.expr())
        from_type = self.get_type(expr)
        to_type = ctx.type_.text
        if from_type == "char" and to_type == "int":
            if isinstance(expr, Literal):
                expr.type = "int"
                return expr
            else:
                temp_result = self.get_temp_var("int")
                self.set_var(temp_result, expr, ctx)
                return temp_result
        elif from_type == "int" and to_type == "char":      
            if isinstance(expr, Literal):
                expr.type = "char"
                expr.value %= 256
                return expr
            else:
                temp_var = self.get_temp_var("int")
                self.set_var(temp_var, Literal(255, "int"), ctx)
                temp_result = self.get_temp_var("char")
                self.set_var(temp_result, expr, ctx)
                self.add_cmd(f"scoreboard players operation #MineScript {temp_result} %= #MineScript {temp_var}", ctx)
                return temp_result        
        
# ! Strings:
# ! /tellraw @a {"storage":"minecraft:minescript","nbt":"text","interpret":true}
# ! /data modify storage datapack:minescript varname set value ["h", "e", "l", "l", "o"]
