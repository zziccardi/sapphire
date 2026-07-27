grammar Sapphire;

// ==========================================
// Parser Rules
// ==========================================

program
    : topLevelItem* EOF
    ;

topLevelItem
    : declaration
    | statement
    | importStatement
    | exportStatement
    ;

importStatement
    : IMPORT identifierPath (AS IDENTIFIER)? SEMICOLON
    ;

exportStatement
    : EXPORT LBRACE (exportSpecifier (COMMA exportSpecifier)* COMMA?)? RBRACE SEMICOLON
    ;

exportSpecifier
    : (IDENTIFIER DOT)? IDENTIFIER (AS IDENTIFIER)?
    ;

identifierPath
    : IDENTIFIER (DOT IDENTIFIER)*
    ;

annotation
    : AT (IDENTIFIER | EXPORT | IMPORT) (LPAREN STRING_LIT RPAREN)?
    ;

declaration
    : structDeclaration
    | enumDeclaration
    | implBlock
    | traitDeclaration
    | functionDeclaration
    | variableDeclarationStatement
    ;

enumDeclaration
    : ENUM IDENTIFIER LBRACE (enumMember (COMMA enumMember)* COMMA?)? RBRACE
    ;

enumMember
    : IDENTIFIER (ASSIGN (INT_LIT | STRING_LIT))?
    ;

structDeclaration
    : (STRUCT | PROTO_KEYWORD) IDENTIFIER (COLON IDENTIFIER)? LBRACE structField* RBRACE
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

returnTypeList
    : type (COMMA type)*
    ;

traitMember
    : annotation* (STATIC | CONST)? FUNC IDENTIFIER LPAREN parameterList? RPAREN (COLON returnTypeList)? SEMICOLON
    ;

functionDeclaration
    : annotation* FUNC functionName LPAREN parameterList? RPAREN (COLON returnTypeList)? block
    ;

functionName
    : IDENTIFIER
    | INIT
    ;

parameterList
    : parameter (COMMA parameter)*
    ;

parameter
    : (VAR | CONST)? (SELF | IDENTIFIER) (COLON type)? (ASSIGN expression)?
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
    | identifierPath
    ;

functionType
    : LPAREN (type (COMMA type)*)? RPAREN ARROW (LPAREN returnTypeList RPAREN | type)
    ;

statement
    : block
    | variableDeclarationStatement
    | assignmentStatement
    | ifStatement
    | whileStatement
    | forStatement
    | returnStatement
    | yieldStatement
    | expressionStatement
    ;

yieldStatement
    : YIELD expression SEMICOLON
    ;

matchExpression
    : MATCH expression LBRACE (matchCase COMMA)* matchCase? COMMA? RBRACE
    ;

matchCase
    : matchPattern ARROW (block | expression)
    ;

matchPattern
    : ELLIPSIS
    | expression
    ;

block
    : LBRACE statement* RBRACE
    ;

varBinding
    : IDENTIFIER (COLON type)?
    ;

varBindingList
    : varBinding (COMMA varBinding)*
    ;

expressionList
    : expression (COMMA expression)*
    ;

variableDeclarationStatement
    : annotation* (LET | VAR) varBindingList (ASSIGN expressionList)? SEMICOLON
    ;

targetList
    : expression (COMMA expression)*
    ;

assignmentStatement
    : targetList (ASSIGN | ADD_ASSIGN | SUB_ASSIGN | MUL_ASSIGN | DIV_ASSIGN | MOD_ASSIGN) expressionList SEMICOLON
    ;

expressionStatement
    : expression SEMICOLON
    ;

returnStatement
    : RETURN (expression (COMMA expression)*)? SEMICOLON
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
    | CLONE expression (LBRACE statement* RBRACE)? (IN expression)?                 # CloneExpr
    | expression (MUL | DIV | MOD) expression                     # MultiplicativeExpr
    | expression (ADD | SUB) expression                           # AdditiveExpr
    | expression (EQ | NEQ | LT | LE | GT | GE) expression        # CompareExpr
    | expression AND expression                                   # LogicalAndExpr
    | expression OR expression                                    # LogicalOrExpr
    | lambdaExpression                                            # LambdaExpr
    | primaryExpression                                           # PrimaryExpr
    ;

lambdaExpression
    : lambdaParameters ARROW type block
    | lambdaParameters ARROW (block | expression)
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
    | structInitializer
    | matchExpression
    ;

structInitializer
    : IDENTIFIER LBRACE structInitFieldList? RBRACE (IN expression)?
    ;

structInitFieldList
    : structInitField (COMMA structInitField)* COMMA?
    ;

structInitField
    : IDENTIFIER ASSIGN expression
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
ENUM : 'enum';
PROTO_KEYWORD : 'proto';
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
MATCH : 'match';
YIELD : 'yield';
TRUE : 'true';
FALSE : 'false';
SELF : 'self';
IMPORT : 'import';
EXPORT : 'export';
AS : 'as';

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
ELLIPSIS : '...';

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
AT : '@';

// Literals & Identifiers
IDENTIFIER : [a-zA-Z_][a-zA-Z0-9_]*;

INT_LIT : [0-9]+;
FLOAT_LIT : [0-9]+ '.' [0-9]+;
STRING_LIT : '"' (~["\\] | '\\' .)* '"';

// Whitespace and Comments
WS : [ \t\r\n]+ -> skip;
LINE_COMMENT : '//' ~[\r\n]* -> skip;
BLOCK_COMMENT : '/*' .*? '*/' -> skip;
