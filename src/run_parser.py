import sys
import os
from antlr4 import *
from antlr4.error.ErrorListener import ErrorListener

try:
    from parser.gen.SapphireLexer import SapphireLexer
    from parser.gen.SapphireParser import SapphireParser
except ModuleNotFoundError:
    from src.parser.gen.SapphireLexer import SapphireLexer
    from src.parser.gen.SapphireParser import SapphireParser


class CustomErrorListener(ErrorListener):
    def __init__(self):
        super().__init__()
        self.errors = 0

    def syntaxError(self, recognizer, offendingSymbol, line, column, msg, e):
        self.errors += 1
        print(f"Error: Line {line}:{column} - {msg}", file=sys.stderr)

def main():
    script_dir = os.path.dirname(os.path.abspath(__file__))
    input_file = os.path.normpath(os.path.join(script_dir, "..", "sample.sp"))
    print(f"Reading source file: {input_file}...")

    try:
        input_stream = FileStream(input_file, encoding='utf-8')
    except Exception as e:
        print(f"Failed to read file: {e}", file=sys.stderr)
        sys.exit(1)

    # Instantiate Lexer
    lexer = SapphireLexer(input_stream)

    # Add custom error listeners
    error_listener = CustomErrorListener()
    lexer.removeErrorListeners()
    lexer.addErrorListener(error_listener)

    # Instantiate Token Stream
    stream = CommonTokenStream(lexer)

    # Instantiate Parser
    parser = SapphireParser(stream)
    parser.removeErrorListeners()
    parser.addErrorListener(error_listener)

    print("Parsing program...")
    tree = parser.program()

    if error_listener.errors > 0:
        print(f"\nParsing completed with {error_listener.errors} error(s).", file=sys.stderr)
        sys.exit(1)
    else:
        print("\nParsing completed successfully with 0 errors!")
        # Print string tree representation
        print("\nParse Tree Preview:")
        # We can print a truncated version of the tree so it doesn't flood the console
        tree_str = tree.toStringTree(recog=parser)
        if len(tree_str) > 500:
            print(tree_str[:500] + " ... [TRUNCATED]")
        else:
            print(tree_str)

if __name__ == '__main__':
    main()
