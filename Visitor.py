import antlr4

from logs import Logger
from MineScriptParser import MineScriptParser
from MineScriptVisitor import MineScriptVisitor

CONTROL_FLOW_CONTEXTS = [MineScriptParser.IfStatementContext,
                         MineScriptParser.ForStatementContext,
                         MineScriptParser.WhileStatementContext]

class Literal:
    def __init__(self, value, type):
        self.value = value
        self.type = type

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
        if self.igfunc is None:
            return name in self.igmemory
        else:
            name = name.replace("+local", "")
            if name in self.local[self.igfunc]:
                return True
            return name in self.igmemory
    
    def get_type(self, name):
        if isinstance(name, Literal):
            return name.type
        else:
            name = name.replace("+local", "")
            if self.igfunc is None:
                return self.igmemory[name]
            else:
                if name in self.local[self.igfunc]:
                    return self.local[self.igfunc][name]
                else:
                    return self.igmemory[name]
        
    def verify_types(self, correct, given, ctx):
        if self.get_type(correct) != self.get_type(given):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Mismatching types: '{self.get_type(correct)}' and '{self.get_type(given)}'", line, char, "error")
            return False
        return True
                
    def add_var(self, name, type_, ctx=None):
        if self.igfunc is None or name.startswith("_"):
            if name not in self.igmemory or ctx is None:
                self.igmemory[name] = type_
            else:
                self.logger.log(f"Multiple definitions of variable '{name}''")
        else:
            if name not in self.local[self.igfunc] or ctx is None:
                self.local[self.igfunc][name] = type_
            else:
                self.logger.log(f"Multiple definitions of variable '{name}''")
            
    def set_var(self, name, value, ctx):
        if isinstance(value, Literal):
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
            if not self.get_type(value).endswith("[]"):
                self.add_cmd(f"scoreboard players operation #MineScript {name} = #MineScript {value}", ctx)
            else:
                self.add_cmd(f"data modify storage {self.name}:minescript {name} set from storage {self.name}:minescript {value}", ctx)
                
    def get_arr_element(self, name, element, ctx):
        if self.get_type(element) != "int":
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"List indexes must be intergers (was {self.get_type(element)})", line, char, "error")
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
        
    def set_arr_element(self, name, element, value, ctx):
        if self.get_type(element) != "int":
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"List indexes must be intergers (was {self.get_type(element)})", line, char, "error")
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
        if isinstance(expr1, Literal) and isinstance(expr2, Literal):
            if self.verify_types(expr1, expr2, ctx):
                return Literal(eval(f"expr1.value{op}expr2.value"), "int")
        elif isinstance(expr1, str) and isinstance(expr2, Literal):
            if self.verify_types(expr1, expr2, ctx):
                temp_result = self.get_temp_var("int")
                self.set_var(temp_result, Literal(0, "int"), ctx)
                if op == "==":
                    self.add_cmd(f"execute if score #MineScript {expr1} matches {expr2.value} run scoreboard players set #MineScript {temp_result} 1", ctx)
                elif op == "<=":
                    self.add_cmd(f"execute if score #MineScript {expr1} matches ..{expr2.value} run scoreboard players set #MineScript {temp_result} 1", ctx)
                elif op == ">=":
                    self.add_cmd(f"execute if score #MineScript {expr1} matches {expr2.value}.. run scoreboard players set #MineScript {temp_result} 1", ctx)
                elif op == "<":
                    self.add_cmd(f"execute unless score #MineScript {expr1} matches {expr2.value}.. run scoreboard players set #MineScript {temp_result} 1", ctx)
                elif op == ">":
                    self.add_cmd(f"execute unless score #MineScript {expr1} matches ..{expr2.value} run scoreboard players set #MineScript {temp_result} 1", ctx)
                elif op == "!=":
                    self.add_cmd(f"execute if score #MineScript {expr1} matches {expr2.value} run scoreboard players set #MineScript {temp_result} 1", ctx)
                self.mark_unused(expr1)
                return temp_result
                        
        elif isinstance(expr2, str) and isinstance(expr1, Literal):
            if op == "==" or op == "!=": newop = op
            elif op == ">=": newop = "<="
            elif op == "<=": newop = ">="
            elif op == ">": newop = "<"
            elif op =="<": newop = ">"
            return self.compare(expr2, expr1, newop, ctx)
        
        elif isinstance(expr1, str) and isinstance(expr2, str):
            if self.verify_types(expr1, expr2, ctx):
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
        if not self.verify_types(expr1, expr2, ctx):
            return
        
        if isinstance(expr1, Literal) and isinstance(expr2, Literal):
            return Literal(eval(f"expr1.value{op}expr2.value"), expr1.type)
        
        elif isinstance(expr1, str) and isinstance(expr2, Literal):
            temp_result = self.get_temp_var(self.get_type(expr2))
            if op == "+":
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players add #MineScript {temp_result} {expr2.value}", ctx)
            elif op == "-":
                self.set_var(temp_result, expr1, ctx)
                self.add_cmd(f"scoreboard players remove #MineScript {temp_result} {expr2.value}", ctx)
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
                        
        elif isinstance(expr2, str) and isinstance(expr1, Literal):
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
            suffix = "" if self.igfunc is None else "+local" 
            self.add_var(name, type_ if dec.arr() is None else type_+"[]", ctx)
            l = dec.expr()
            if l is not None:
                value = self.visit(l)
                if self.verify_types(value, name, l):
                    self.set_var(name+suffix, value, ctx)
                if isinstance(value, str):
                    self.mark_unused(value)
                    
    def visitVariableAssignement(self, ctx):
        name = ctx.WORD().getText()
        if not self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
        else:
            suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
            if ctx.expr() is not None:
                value = self.visit(ctx.expr())
                if ctx.arr() is None:
                    if not self.verify_types(name, value, ctx):
                        return
                    self.set_var(name+suffix, value, ctx)
                else:
                    element = self.visit(ctx.arr().expr())
                    self.igmemory["_temp"] = self.get_type(name)[:-2]
                    if not self.verify_types("_temp", element, ctx):
                        return
                    self.set_arr_element(name+suffix, element, value, ctx)
                    del self.igmemory["_temp"]
                    if isinstance(element, str):
                        self.mark_unused(element)
                if isinstance(value, str):
                    self.mark_unused(value)
                
            if ctx.arr() is not None and self.is_used(ctx):
                return self.get_arr_element(name+suffix, self.visit(ctx.arr().expr()), ctx)
            elif ctx.arr() is None and self.is_used_on_condition(ctx):
                temp_result = self.get_temp_var(self.get_type(name))
                self.set_var(temp_result, name+suffix, ctx)
                return temp_result
            else:
                return name+suffix
            
    def visitArray(self, ctx):
        arr = []
        arr_type = None
        for expr in ctx.expr():
            value = self.visit(expr)
            if arr_type is None:
                arr_type = value
            else:
                if not self.verify_types(arr_type, value, expr):
                    return
            arr.append(value)
        if self.is_used(ctx):
            temp_result = self.get_temp_var(self.get_type(arr_type) + "[]")
            self.set_var(temp_result, Literal(arr, self.get_type(arr_type) + "[]"), ctx)
            return temp_result
                    
    def visitFunctionDeclaration(self, ctx):
        name = ctx.WORD().getText()
        self.igfunc = name
        self.local[self.igfunc] = {}
        self.igfuncinfo = {"break": self.get_temp_var("int")}
        self.set_var(self.igfuncinfo['break'], Literal(0, "int"), ctx)
        self.prefixes.append(f"unless score #MineScript {self.igfuncinfo['break']} matches 1")
        self.visit(ctx.stat())
        self.prefixes.pop(-1)
        self.mark_unused(self.igfuncinfo['break'])
        self.igfuncinfo = None
        self.igfunc = None
        
    def visitFunctionCall(self, ctx):
        name = ctx.WORD().getText()
        if name not in self.igfunctions:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undefined function '{name}'", line, char, "error")
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
            else:
                error = False
                for i in range(len(args)):
                    if not self.get_type(args[i][0]) == fargs[i][1]:
                        msg = (f"Argument '{fargs[i][0]}' is of type '{fargs[i][1]}', "
                                f"but '{self.get_type(args[i][0])}' was provided.")
                        self.logger.log(msg, args[i][1], args[i][2], "error")
                        error = True
                        break
                if not error:
                    self.add_cmd(f"function {self.name}:{name}", ctx)
            if "return" in self.igfunctions[name]:
                return self.igfunctions[name]["return"]
            
    def visitReturnStatement(self, ctx):
        if self.igfunc is None:
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log("Return outside function", line, char, "error")
        else:
            if "return" in self.igfunctions[self.igfunc]:
                if ctx.expr() is None:
                    line = ctx.stop.line
                    char = ctx.stop.column
                    self.logger.log("No return value for non-void function", line, char, "error")
                else:
                    value = self.visit(ctx.expr())
                    if self.verify_types(self.igfunctions[self.igfunc]["return"], value, ctx.expr()):        
                        self.set_var(self.igfunctions[self.igfunc]["return"], value, ctx)
                        self.add_cmd(f"scoreboard players set #MineScript {self.igfuncinfo['break']} 1", ctx)
                    if isinstance(value, str):
                        self.mark_unused(value)
            else:
                if ctx.expr() is not None:
                    line = ctx.stop.line
                    char = ctx.stop.column
                    self.logger.log("Void function returns a value", line, char, "error")
                else:
                    self.add_cmd(f"scoreboard players set #MineScript {self.igfuncinfo['break']} 1", ctx)
                    
    def visitLiteral(self, ctx):
        if ctx.CHAR() is not None:
            return Literal(eval(f"ord({ctx.CHAR().getText()})"), "char")
        elif ctx.NUMBER() is not None:
            return Literal(int(ctx.NUMBER().getText()), "int")
        elif ctx.STRING() is not None:
            return Literal(ctx.STRING().getText()[1:-1], "char[]")
        
    def visitVariableIncrementPos(self, ctx):
        name = ctx.WORD().getText()
        if not self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
        else:
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
        if not self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
        else:
            suffix = "" if self.igfunc is None or name not in self.local[self.igfunc] else "+local" 
            self.add_cmd(f"scoreboard players add #MineScript {name}{suffix} 1", ctx)
            return name+suffix
        
    def visitVariableDecrementPos(self, ctx):
        name = ctx.WORD().getText()
        if not self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
        else:
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
        if self.is_defined(name):
            line = ctx.start.line
            char = ctx.start.column
            self.logger.log(f"Undeclared variable '{name}'", line, char, "error")
        else:
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
        print(self.local)
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
            return

        self.set_var(self.break_var[-1], Literal(0, "int"), ctx)
        
    def visitPrintStatement(self, ctx):
        if len(ctx.expr()) < 3:
            line = ctx.start.line
            char = ctx.stop.column
            msg = (f"Built-in function 'print' takes at least 3 arguments, "
                   f"but only {len(ctx.expr())} {'was' if len(ctx.expr()) == 1 else 'were'} given")
            self.logger.log(msg, line, char, "error")
        selector, color, *args = ctx.expr()
        selector_value = self.visit(selector)
        color_value = self.visit(color)
        if isinstance(selector_value, Literal) and selector_value.type == "char[]":
            if isinstance(color_value, Literal) and color_value.type == "char[]":
                pass
            else:
                line = color.start.line
                char = color.stop.column
                self.logger.log("The second argument of 'print' must be a string "
                                "evaluated at compile time.", line, char, "error")
        else:
            line = selector.start.line
            char = selector.stop.column
            self.logger.log("The first argument of 'print' must be a string "
                            "evaluated at compile time.", line, char, "error")
        
        color_text = f"\"color\":\"{color_value.value}\""
        command = ""
        for arg in args:
            arg_value = self.visit(arg)
            if isinstance(arg_value, Literal):
                command += ',{"text":'
                if self.get_type(arg_value) == "char":
                    command += f'"{chr(arg_value.value)}"'
                else:
                    command += f'"{str(arg_value.value)}"'
                command += ", " + color_text + "}"
            else:
                if self.get_type(arg_value) == "int":
                    command += ',{"score":{"name":"#MineScript","objective":"'+arg_value+'"}}'
                self.mark_unused(arg_value)
        self.add_cmd(f"tellraw {selector_value.value} [{command[1:]}]", ctx)
        
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