grammar Sapphire;

// ==========================================
// Parser Rules
// ==========================================

program
    : declaration* EOF
    ;

declaration
    : structDeclaration
    | implBlock
    | traitDeclaration
    | functionDeclaration
    | variableDeclarationStatement
    ;

structDeclaration
    : STRUCT IDENTIFIER (COLON IDENTIFIER)? LBRACE structField* RBRACE
    ;

structField
    : (LET | VAR) IDENTIFIER COLON type (ASSIGN expression)? SEMICOLON
    ;

implBlock
    : IMPL (traitName=IDENTIFIER FOR)? structName=IDENTIFIER LBRACE implMember* RBRACE
    ;

implMember
    : (STATIC | CONST)? functionDeclaration
    ;

traitDeclaration
    : TRAIT IDENTIFIER LBRACE traitMember* RBRACE
    ;

traitMember
    : FUNC IDENTIFIER LPAREN parameterList? RPAREN (COLON type)? SEMICOLON
    ;

functionDeclaration
    : FUNC functionName LPAREN parameterList? RPAREN (COLON type)? block
    ;

functionName
    : IDENTIFIER
    | INIT
    ;

parameterList
    : parameter (COMMA parameter)*
    ;

parameter
    : VAR? IDENTIFIER COLON type (ASSIGN expression)?
    ;

type
    : baseType
    | functionType
    | type QUESTION
    ;

baseType
    : INT_TYPE
    | FLOAT_TYPE
    | BOOL_TYPE
    | IDENTIFIER
    ;

functionType
    : LPAREN (type (COMMA type)*)? RPAREN ARROW type
    ;

statement
    : block
    | variableDeclarationStatement
    | assignmentStatement
    | ifStatement
    | whileStatement
    | forStatement
    | returnStatement
    | expressionStatement
    ;

block
    : LBRACE statement* RBRACE
    ;

variableDeclarationStatement
    : (LET | VAR) IDENTIFIER (COLON type)? ASSIGN expression SEMICOLON
    ;

assignmentStatement
    : expression (ASSIGN | ADD_ASSIGN | SUB_ASSIGN | MUL_ASSIGN | DIV_ASSIGN | MOD_ASSIGN) expression SEMICOLON
    ;

expressionStatement
    : expression SEMICOLON
    ;

returnStatement
    : RETURN expression? SEMICOLON
    ;

ifStatement
    : IF expression block (ELSE ifStatement | ELSE block)?
    | IF LET IDENTIFIER ASSIGN expression block (ELSE ifStatement | ELSE block)?
    ;

whileStatement
    : WHILE expression block
    ;

forStatement
    : FOR VAR? IDENTIFIER IN expression block
    ;

expression
    : expression LBRACKET expression RBRACKET                     # IndexExpr
    | expression LPAREN argumentList? RPAREN                      # CallExpr
    | expression (DOT | OPT_DOT) memberAccess                     # MemberAccessExpr
    | (SUB | ADD | NOT) expression                                # UnaryExpr
    | CLONE expression (LBRACE statement* RBRACE)?                 # CloneExpr
    | expression (MUL | DIV | MOD) expression                     # MultiplicativeExpr
    | expression (ADD | SUB) expression                           # AdditiveExpr
    | expression (EQ | NEQ | LT | LE | GT | GE) expression        # CompareExpr
    | expression AND expression                                   # LogicalAndExpr
    | expression OR expression                                    # LogicalOrExpr
    | lambdaExpression                                            # LambdaExpr
    | primaryExpression                                           # PrimaryExpr
    ;

lambdaExpression
    : lambdaParameters ARROW type? (block | expression)
    ;

lambdaParameters
    : IDENTIFIER
    | LPAREN (lambdaParameter (COMMA lambdaParameter)*)? RPAREN
    ;

lambdaParameter
    : IDENTIFIER (COLON type)?
    ;

argumentList
    : argument (COMMA argument)*
    ;

argument
    : IDENTIFIER ASSIGN expression
    | expression
    ;

memberAccess
    : IDENTIFIER
    | PROTO
    | INIT
    ;

primaryExpression
    : literal
    | IDENTIFIER
    | SELF
    | arrayLiteral
    | LPAREN expression RPAREN
    ;

literal
    : INT_LIT
    | FLOAT_LIT
    | STRING_LIT
    | TRUE
    | FALSE
    | NONE
    ;

arrayLiteral
    : LBRACKET (expression (COMMA expression)* COMMA?)? RBRACKET
    ;


// ==========================================
// Lexer Rules
// ==========================================

// Keywords
LET : 'let';
VAR : 'var';
FUNC : 'func';
STRUCT : 'struct';
IMPL : 'impl';
TRAIT : 'trait';
FOR : 'for';
IN : 'in';
STATIC : 'static';
CONST : 'const';
CLONE : 'clone';
IF : 'if';
ELSE : 'else';
WHILE : 'while';
NONE : 'none';
RETURN : 'return';
TRUE : 'true';
FALSE : 'false';
SELF : 'self';

// Special keywords/identifiers
INIT : '__init__';
PROTO : '__proto__';

// Primitive Types
INT_TYPE : 'int';
FLOAT_TYPE : 'float';
BOOL_TYPE : 'bool';

// Operators
ASSIGN : '=';
ADD_ASSIGN : '+=';
SUB_ASSIGN : '-=';
MUL_ASSIGN : '*=';
DIV_ASSIGN : '/=';
MOD_ASSIGN : '%=';

ARROW : '->';
COLON : ':';
QUESTION : '?';
SEMICOLON : ';';
COMMA : ',';
DOT : '.';
OPT_DOT : '?.';

EQ : '==';
NEQ : '!=';
LT : '<';
LE : '<=';
GT : '>';
GE : '>=';

ADD : '+';
SUB : '-';
MUL : '*';
DIV : '/';
MOD : '%';

AND : '&&';
OR : '||';
NOT : '!';

LPAREN : '(';
RPAREN : ')';
LBRACE : '{';
RBRACE : '}';
LBRACKET : '[';
RBRACKET : ']';

// Literals & Identifiers
IDENTIFIER : [a-zA-Z_][a-zA-Z0-9_]*;

INT_LIT : [0-9]+;
FLOAT_LIT : [0-9]+ '.' [0-9]+;
STRING_LIT : '"' (~["\\] | '\\' .)* '"';

// Whitespace and Comments
WS : [ \t\r\n]+ -> skip;
LINE_COMMENT : '//' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
