grammar MineScript;

/* Grammar rules */

prog                    : stat* EOF
                        ;

stat
                        : expr SEP                  
                        | variableDeclaration SEP   
                        | ifStatement               
                        | forStatement              
                        | whileStatement            
                        | functionDeclaration
                        | printStatement
                        | breakStatement  
                        | returnStatement
                        | '{' stat* '}'             
                        ;

expr
                        : variableAssignement   #ignore
                        | '(' expr ')'          #parentheses
                        | variableDecrementPos  #ignore
                        | variableDecrementPre  #ignore
                        | variableIncrementPos  #ignore
                        | variableIncrementPre  #ignore
                        | K_MC '(' expr ')'         #mcCommand
                        | K_RESULT '(' expr ')'     #resultCommand
                        | K_SUCCESS '(' expr ')'    #successCommand
                        | functionCall          #ignore
                        | cast                  #ignore
                        | expr type_=(OP_EQ|OP_GE|OP_LE|OP_GT|OP_LT|OP_DIF) expr        #variableComparison
                        | expr type_=(OP_MULT|OP_MOD|OP_DIV) expr                       #variableOperation
                        | expr type_=(OP_PLUS|OP_MINUS) expr                            #variableOperation
                        | literal               #ignore
                        | array                 #ignore
                        ;

cast                    : '(' type_=(K_INT | K_CHAR) ')' expr;
variableDeclaration     : type_=(K_INT | K_CHAR) variableAssignement (COMMA variableAssignement)*;
variableAssignement     : PREFIX? WORD arr? (OP_ASSIGN expr)?;
functionDeclaration     : type_=(K_INT | K_CHAR | K_VOID) WORD '(' (functionArg (COMMA functionArg)*)? ')' stat;
functionArg             : type_=(K_INT | K_CHAR) PREFIX? WORD arr?;
printStatement          : K_PRINT '(' (expr (COMMA expr)*)? ')' SEP;
functionCall            : PREFIX? WORD '(' (expr (COMMA expr)*)? ')';
variableIncrementPre    : OP_INC PREFIX? WORD;
variableIncrementPos    : PREFIX? WORD OP_INC;
variableDecrementPre    : OP_DEC PREFIX? WORD;
variableDecrementPos    : PREFIX? WORD OP_DEC;
literal                 : STRING | NUMBER | CHAR;
array                   : '{' (expr (COMMA expr)*)? '}';
arr                     : '[' (expr)? ']';
breakStatement          : K_BREAK SEP;
returnStatement         : K_RETURN expr? SEP;

ifStatement             : K_IF '(' expr ')' stat (K_ELSE stat)?;
forStatement            : K_FOR '(' (expr | variableDeclaration) SEP expr SEP expr ')' stat;
whileStatement          : K_WHILE '(' expr ')' stat;


/* Lexer rules */

STRING                  : '"' (~('"' | '\n') | '\\"')* '"';
PREFIX                  : '$';
K_VOID                  : 'void';
K_INT                   : 'int';
K_CHAR                  : 'char';
K_FOR                   : 'for';
K_WHILE                 : 'while';
K_BREAK                 : 'break';
K_IF                    : 'if';
K_ELSE                  : 'else';
K_PRINT                 : 'print';
K_MC                    : 'mc';
K_RESULT                : 'result';
K_SUCCESS               : 'success';
K_RETURN                : 'return';
OP_INC                  : '++';
OP_DEC                  : '--';
OP_PLUS                 : '+';
OP_MINUS                : '-';
OP_MULT                 : '*';
OP_MOD                  : '%';
OP_DIV                  : '/';
OP_ASSIGN               : '=';
OP_EQ                   : '==';
OP_GE                   : '>=';
OP_LE                   : '<=';
OP_GT                   : '>';
OP_LT                   : '<';
OP_DIF                  : '!=';
COMMA                   : ',';
WORD                    : [a-zA-Z] [a-zA-Z_0-9]*;
fragment DIGIT          : [0-9];
NUMBER                  : '-'? DIGIT+ ('.' DIGIT+)?;
CHAR                    : '\'' (~('\'' | '\n') | '\\\'' | '\\n' | '\\0' | '\\t')? '\'';
WHITESPACE              : (' ' | '\t' | '\n' | '\r') -> skip;
COMMENT                 : '//' ~[\r\n]* -> skip;
MLCOMMENT               : '/*' .*? '*/' -> skip;
SEP                     : ';';