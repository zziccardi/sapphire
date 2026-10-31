# Generated from grammar/Sapphire.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .SapphireParser import SapphireParser
else:
    from SapphireParser import SapphireParser

# This class defines a complete listener for a parse tree produced by SapphireParser.
class SapphireListener(ParseTreeListener):

    # Enter a parse tree produced by SapphireParser#program.
    def enterProgram(self, ctx:SapphireParser.ProgramContext):
        pass

    # Exit a parse tree produced by SapphireParser#program.
    def exitProgram(self, ctx:SapphireParser.ProgramContext):
        pass


    # Enter a parse tree produced by SapphireParser#topLevelItem.
    def enterTopLevelItem(self, ctx:SapphireParser.TopLevelItemContext):
        pass

    # Exit a parse tree produced by SapphireParser#topLevelItem.
    def exitTopLevelItem(self, ctx:SapphireParser.TopLevelItemContext):
        pass


    # Enter a parse tree produced by SapphireParser#importStatement.
    def enterImportStatement(self, ctx:SapphireParser.ImportStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#importStatement.
    def exitImportStatement(self, ctx:SapphireParser.ImportStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#exportStatement.
    def enterExportStatement(self, ctx:SapphireParser.ExportStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#exportStatement.
    def exitExportStatement(self, ctx:SapphireParser.ExportStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#exportSpecifier.
    def enterExportSpecifier(self, ctx:SapphireParser.ExportSpecifierContext):
        pass

    # Exit a parse tree produced by SapphireParser#exportSpecifier.
    def exitExportSpecifier(self, ctx:SapphireParser.ExportSpecifierContext):
        pass


    # Enter a parse tree produced by SapphireParser#identifierPath.
    def enterIdentifierPath(self, ctx:SapphireParser.IdentifierPathContext):
        pass

    # Exit a parse tree produced by SapphireParser#identifierPath.
    def exitIdentifierPath(self, ctx:SapphireParser.IdentifierPathContext):
        pass


    # Enter a parse tree produced by SapphireParser#annotation.
    def enterAnnotation(self, ctx:SapphireParser.AnnotationContext):
        pass

    # Exit a parse tree produced by SapphireParser#annotation.
    def exitAnnotation(self, ctx:SapphireParser.AnnotationContext):
        pass


    # Enter a parse tree produced by SapphireParser#declaration.
    def enterDeclaration(self, ctx:SapphireParser.DeclarationContext):
        pass

    # Exit a parse tree produced by SapphireParser#declaration.
    def exitDeclaration(self, ctx:SapphireParser.DeclarationContext):
        pass


    # Enter a parse tree produced by SapphireParser#enumDeclaration.
    def enterEnumDeclaration(self, ctx:SapphireParser.EnumDeclarationContext):
        pass

    # Exit a parse tree produced by SapphireParser#enumDeclaration.
    def exitEnumDeclaration(self, ctx:SapphireParser.EnumDeclarationContext):
        pass


    # Enter a parse tree produced by SapphireParser#enumMember.
    def enterEnumMember(self, ctx:SapphireParser.EnumMemberContext):
        pass

    # Exit a parse tree produced by SapphireParser#enumMember.
    def exitEnumMember(self, ctx:SapphireParser.EnumMemberContext):
        pass


    # Enter a parse tree produced by SapphireParser#typeParamList.
    def enterTypeParamList(self, ctx:SapphireParser.TypeParamListContext):
        pass

    # Exit a parse tree produced by SapphireParser#typeParamList.
    def exitTypeParamList(self, ctx:SapphireParser.TypeParamListContext):
        pass


    # Enter a parse tree produced by SapphireParser#typeArgumentList.
    def enterTypeArgumentList(self, ctx:SapphireParser.TypeArgumentListContext):
        pass

    # Exit a parse tree produced by SapphireParser#typeArgumentList.
    def exitTypeArgumentList(self, ctx:SapphireParser.TypeArgumentListContext):
        pass


    # Enter a parse tree produced by SapphireParser#structDeclaration.
    def enterStructDeclaration(self, ctx:SapphireParser.StructDeclarationContext):
        pass

    # Exit a parse tree produced by SapphireParser#structDeclaration.
    def exitStructDeclaration(self, ctx:SapphireParser.StructDeclarationContext):
        pass


    # Enter a parse tree produced by SapphireParser#structField.
    def enterStructField(self, ctx:SapphireParser.StructFieldContext):
        pass

    # Exit a parse tree produced by SapphireParser#structField.
    def exitStructField(self, ctx:SapphireParser.StructFieldContext):
        pass


    # Enter a parse tree produced by SapphireParser#implBlock.
    def enterImplBlock(self, ctx:SapphireParser.ImplBlockContext):
        pass

    # Exit a parse tree produced by SapphireParser#implBlock.
    def exitImplBlock(self, ctx:SapphireParser.ImplBlockContext):
        pass


    # Enter a parse tree produced by SapphireParser#implMember.
    def enterImplMember(self, ctx:SapphireParser.ImplMemberContext):
        pass

    # Exit a parse tree produced by SapphireParser#implMember.
    def exitImplMember(self, ctx:SapphireParser.ImplMemberContext):
        pass


    # Enter a parse tree produced by SapphireParser#traitDeclaration.
    def enterTraitDeclaration(self, ctx:SapphireParser.TraitDeclarationContext):
        pass

    # Exit a parse tree produced by SapphireParser#traitDeclaration.
    def exitTraitDeclaration(self, ctx:SapphireParser.TraitDeclarationContext):
        pass


    # Enter a parse tree produced by SapphireParser#returnTypeList.
    def enterReturnTypeList(self, ctx:SapphireParser.ReturnTypeListContext):
        pass

    # Exit a parse tree produced by SapphireParser#returnTypeList.
    def exitReturnTypeList(self, ctx:SapphireParser.ReturnTypeListContext):
        pass


    # Enter a parse tree produced by SapphireParser#traitMember.
    def enterTraitMember(self, ctx:SapphireParser.TraitMemberContext):
        pass

    # Exit a parse tree produced by SapphireParser#traitMember.
    def exitTraitMember(self, ctx:SapphireParser.TraitMemberContext):
        pass


    # Enter a parse tree produced by SapphireParser#functionDeclaration.
    def enterFunctionDeclaration(self, ctx:SapphireParser.FunctionDeclarationContext):
        pass

    # Exit a parse tree produced by SapphireParser#functionDeclaration.
    def exitFunctionDeclaration(self, ctx:SapphireParser.FunctionDeclarationContext):
        pass


    # Enter a parse tree produced by SapphireParser#baseInitializerList.
    def enterBaseInitializerList(self, ctx:SapphireParser.BaseInitializerListContext):
        pass

    # Exit a parse tree produced by SapphireParser#baseInitializerList.
    def exitBaseInitializerList(self, ctx:SapphireParser.BaseInitializerListContext):
        pass


    # Enter a parse tree produced by SapphireParser#baseInitializer.
    def enterBaseInitializer(self, ctx:SapphireParser.BaseInitializerContext):
        pass

    # Exit a parse tree produced by SapphireParser#baseInitializer.
    def exitBaseInitializer(self, ctx:SapphireParser.BaseInitializerContext):
        pass


    # Enter a parse tree produced by SapphireParser#functionName.
    def enterFunctionName(self, ctx:SapphireParser.FunctionNameContext):
        pass

    # Exit a parse tree produced by SapphireParser#functionName.
    def exitFunctionName(self, ctx:SapphireParser.FunctionNameContext):
        pass


    # Enter a parse tree produced by SapphireParser#parameterList.
    def enterParameterList(self, ctx:SapphireParser.ParameterListContext):
        pass

    # Exit a parse tree produced by SapphireParser#parameterList.
    def exitParameterList(self, ctx:SapphireParser.ParameterListContext):
        pass


    # Enter a parse tree produced by SapphireParser#parameter.
    def enterParameter(self, ctx:SapphireParser.ParameterContext):
        pass

    # Exit a parse tree produced by SapphireParser#parameter.
    def exitParameter(self, ctx:SapphireParser.ParameterContext):
        pass


    # Enter a parse tree produced by SapphireParser#type.
    def enterType(self, ctx:SapphireParser.TypeContext):
        pass

    # Exit a parse tree produced by SapphireParser#type.
    def exitType(self, ctx:SapphireParser.TypeContext):
        pass


    # Enter a parse tree produced by SapphireParser#collectionType.
    def enterCollectionType(self, ctx:SapphireParser.CollectionTypeContext):
        pass

    # Exit a parse tree produced by SapphireParser#collectionType.
    def exitCollectionType(self, ctx:SapphireParser.CollectionTypeContext):
        pass


    # Enter a parse tree produced by SapphireParser#baseType.
    def enterBaseType(self, ctx:SapphireParser.BaseTypeContext):
        pass

    # Exit a parse tree produced by SapphireParser#baseType.
    def exitBaseType(self, ctx:SapphireParser.BaseTypeContext):
        pass


    # Enter a parse tree produced by SapphireParser#functionType.
    def enterFunctionType(self, ctx:SapphireParser.FunctionTypeContext):
        pass

    # Exit a parse tree produced by SapphireParser#functionType.
    def exitFunctionType(self, ctx:SapphireParser.FunctionTypeContext):
        pass


    # Enter a parse tree produced by SapphireParser#statement.
    def enterStatement(self, ctx:SapphireParser.StatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#statement.
    def exitStatement(self, ctx:SapphireParser.StatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#matchStatement.
    def enterMatchStatement(self, ctx:SapphireParser.MatchStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#matchStatement.
    def exitMatchStatement(self, ctx:SapphireParser.MatchStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#breakStatement.
    def enterBreakStatement(self, ctx:SapphireParser.BreakStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#breakStatement.
    def exitBreakStatement(self, ctx:SapphireParser.BreakStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#continueStatement.
    def enterContinueStatement(self, ctx:SapphireParser.ContinueStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#continueStatement.
    def exitContinueStatement(self, ctx:SapphireParser.ContinueStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#yieldStatement.
    def enterYieldStatement(self, ctx:SapphireParser.YieldStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#yieldStatement.
    def exitYieldStatement(self, ctx:SapphireParser.YieldStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#matchExpression.
    def enterMatchExpression(self, ctx:SapphireParser.MatchExpressionContext):
        pass

    # Exit a parse tree produced by SapphireParser#matchExpression.
    def exitMatchExpression(self, ctx:SapphireParser.MatchExpressionContext):
        pass


    # Enter a parse tree produced by SapphireParser#matchCase.
    def enterMatchCase(self, ctx:SapphireParser.MatchCaseContext):
        pass

    # Exit a parse tree produced by SapphireParser#matchCase.
    def exitMatchCase(self, ctx:SapphireParser.MatchCaseContext):
        pass


    # Enter a parse tree produced by SapphireParser#matchPattern.
    def enterMatchPattern(self, ctx:SapphireParser.MatchPatternContext):
        pass

    # Exit a parse tree produced by SapphireParser#matchPattern.
    def exitMatchPattern(self, ctx:SapphireParser.MatchPatternContext):
        pass


    # Enter a parse tree produced by SapphireParser#block.
    def enterBlock(self, ctx:SapphireParser.BlockContext):
        pass

    # Exit a parse tree produced by SapphireParser#block.
    def exitBlock(self, ctx:SapphireParser.BlockContext):
        pass


    # Enter a parse tree produced by SapphireParser#varBinding.
    def enterVarBinding(self, ctx:SapphireParser.VarBindingContext):
        pass

    # Exit a parse tree produced by SapphireParser#varBinding.
    def exitVarBinding(self, ctx:SapphireParser.VarBindingContext):
        pass


    # Enter a parse tree produced by SapphireParser#varBindingList.
    def enterVarBindingList(self, ctx:SapphireParser.VarBindingListContext):
        pass

    # Exit a parse tree produced by SapphireParser#varBindingList.
    def exitVarBindingList(self, ctx:SapphireParser.VarBindingListContext):
        pass


    # Enter a parse tree produced by SapphireParser#expressionList.
    def enterExpressionList(self, ctx:SapphireParser.ExpressionListContext):
        pass

    # Exit a parse tree produced by SapphireParser#expressionList.
    def exitExpressionList(self, ctx:SapphireParser.ExpressionListContext):
        pass


    # Enter a parse tree produced by SapphireParser#variableDeclarationStatement.
    def enterVariableDeclarationStatement(self, ctx:SapphireParser.VariableDeclarationStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#variableDeclarationStatement.
    def exitVariableDeclarationStatement(self, ctx:SapphireParser.VariableDeclarationStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#targetList.
    def enterTargetList(self, ctx:SapphireParser.TargetListContext):
        pass

    # Exit a parse tree produced by SapphireParser#targetList.
    def exitTargetList(self, ctx:SapphireParser.TargetListContext):
        pass


    # Enter a parse tree produced by SapphireParser#assignmentStatement.
    def enterAssignmentStatement(self, ctx:SapphireParser.AssignmentStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#assignmentStatement.
    def exitAssignmentStatement(self, ctx:SapphireParser.AssignmentStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#expressionStatement.
    def enterExpressionStatement(self, ctx:SapphireParser.ExpressionStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#expressionStatement.
    def exitExpressionStatement(self, ctx:SapphireParser.ExpressionStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#returnStatement.
    def enterReturnStatement(self, ctx:SapphireParser.ReturnStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#returnStatement.
    def exitReturnStatement(self, ctx:SapphireParser.ReturnStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#ifStatement.
    def enterIfStatement(self, ctx:SapphireParser.IfStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#ifStatement.
    def exitIfStatement(self, ctx:SapphireParser.IfStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#guardStatement.
    def enterGuardStatement(self, ctx:SapphireParser.GuardStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#guardStatement.
    def exitGuardStatement(self, ctx:SapphireParser.GuardStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#whileStatement.
    def enterWhileStatement(self, ctx:SapphireParser.WhileStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#whileStatement.
    def exitWhileStatement(self, ctx:SapphireParser.WhileStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#letOrVarBinding.
    def enterLetOrVarBinding(self, ctx:SapphireParser.LetOrVarBindingContext):
        pass

    # Exit a parse tree produced by SapphireParser#letOrVarBinding.
    def exitLetOrVarBinding(self, ctx:SapphireParser.LetOrVarBindingContext):
        pass


    # Enter a parse tree produced by SapphireParser#forStatement.
    def enterForStatement(self, ctx:SapphireParser.ForStatementContext):
        pass

    # Exit a parse tree produced by SapphireParser#forStatement.
    def exitForStatement(self, ctx:SapphireParser.ForStatementContext):
        pass


    # Enter a parse tree produced by SapphireParser#CoalesceExpr.
    def enterCoalesceExpr(self, ctx:SapphireParser.CoalesceExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#CoalesceExpr.
    def exitCoalesceExpr(self, ctx:SapphireParser.CoalesceExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#LambdaExpr.
    def enterLambdaExpr(self, ctx:SapphireParser.LambdaExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#LambdaExpr.
    def exitLambdaExpr(self, ctx:SapphireParser.LambdaExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#UnaryExpr.
    def enterUnaryExpr(self, ctx:SapphireParser.UnaryExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#UnaryExpr.
    def exitUnaryExpr(self, ctx:SapphireParser.UnaryExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#LogicalAndExpr.
    def enterLogicalAndExpr(self, ctx:SapphireParser.LogicalAndExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#LogicalAndExpr.
    def exitLogicalAndExpr(self, ctx:SapphireParser.LogicalAndExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#IndexExpr.
    def enterIndexExpr(self, ctx:SapphireParser.IndexExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#IndexExpr.
    def exitIndexExpr(self, ctx:SapphireParser.IndexExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#MultiplicativeExpr.
    def enterMultiplicativeExpr(self, ctx:SapphireParser.MultiplicativeExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#MultiplicativeExpr.
    def exitMultiplicativeExpr(self, ctx:SapphireParser.MultiplicativeExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#LogicalOrExpr.
    def enterLogicalOrExpr(self, ctx:SapphireParser.LogicalOrExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#LogicalOrExpr.
    def exitLogicalOrExpr(self, ctx:SapphireParser.LogicalOrExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#CloneExpr.
    def enterCloneExpr(self, ctx:SapphireParser.CloneExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#CloneExpr.
    def exitCloneExpr(self, ctx:SapphireParser.CloneExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#AdditiveExpr.
    def enterAdditiveExpr(self, ctx:SapphireParser.AdditiveExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#AdditiveExpr.
    def exitAdditiveExpr(self, ctx:SapphireParser.AdditiveExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#CompareExpr.
    def enterCompareExpr(self, ctx:SapphireParser.CompareExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#CompareExpr.
    def exitCompareExpr(self, ctx:SapphireParser.CompareExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#CastExpr.
    def enterCastExpr(self, ctx:SapphireParser.CastExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#CastExpr.
    def exitCastExpr(self, ctx:SapphireParser.CastExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#PrimaryExpr.
    def enterPrimaryExpr(self, ctx:SapphireParser.PrimaryExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#PrimaryExpr.
    def exitPrimaryExpr(self, ctx:SapphireParser.PrimaryExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#CallExpr.
    def enterCallExpr(self, ctx:SapphireParser.CallExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#CallExpr.
    def exitCallExpr(self, ctx:SapphireParser.CallExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#MoveExpr.
    def enterMoveExpr(self, ctx:SapphireParser.MoveExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#MoveExpr.
    def exitMoveExpr(self, ctx:SapphireParser.MoveExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#MemberAccessExpr.
    def enterMemberAccessExpr(self, ctx:SapphireParser.MemberAccessExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#MemberAccessExpr.
    def exitMemberAccessExpr(self, ctx:SapphireParser.MemberAccessExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#TernaryExpr.
    def enterTernaryExpr(self, ctx:SapphireParser.TernaryExprContext):
        pass

    # Exit a parse tree produced by SapphireParser#TernaryExpr.
    def exitTernaryExpr(self, ctx:SapphireParser.TernaryExprContext):
        pass


    # Enter a parse tree produced by SapphireParser#lambdaExpression.
    def enterLambdaExpression(self, ctx:SapphireParser.LambdaExpressionContext):
        pass

    # Exit a parse tree produced by SapphireParser#lambdaExpression.
    def exitLambdaExpression(self, ctx:SapphireParser.LambdaExpressionContext):
        pass


    # Enter a parse tree produced by SapphireParser#lambdaParameters.
    def enterLambdaParameters(self, ctx:SapphireParser.LambdaParametersContext):
        pass

    # Exit a parse tree produced by SapphireParser#lambdaParameters.
    def exitLambdaParameters(self, ctx:SapphireParser.LambdaParametersContext):
        pass


    # Enter a parse tree produced by SapphireParser#lambdaParameter.
    def enterLambdaParameter(self, ctx:SapphireParser.LambdaParameterContext):
        pass

    # Exit a parse tree produced by SapphireParser#lambdaParameter.
    def exitLambdaParameter(self, ctx:SapphireParser.LambdaParameterContext):
        pass


    # Enter a parse tree produced by SapphireParser#argumentList.
    def enterArgumentList(self, ctx:SapphireParser.ArgumentListContext):
        pass

    # Exit a parse tree produced by SapphireParser#argumentList.
    def exitArgumentList(self, ctx:SapphireParser.ArgumentListContext):
        pass


    # Enter a parse tree produced by SapphireParser#argument.
    def enterArgument(self, ctx:SapphireParser.ArgumentContext):
        pass

    # Exit a parse tree produced by SapphireParser#argument.
    def exitArgument(self, ctx:SapphireParser.ArgumentContext):
        pass


    # Enter a parse tree produced by SapphireParser#memberAccess.
    def enterMemberAccess(self, ctx:SapphireParser.MemberAccessContext):
        pass

    # Exit a parse tree produced by SapphireParser#memberAccess.
    def exitMemberAccess(self, ctx:SapphireParser.MemberAccessContext):
        pass


    # Enter a parse tree produced by SapphireParser#primaryExpression.
    def enterPrimaryExpression(self, ctx:SapphireParser.PrimaryExpressionContext):
        pass

    # Exit a parse tree produced by SapphireParser#primaryExpression.
    def exitPrimaryExpression(self, ctx:SapphireParser.PrimaryExpressionContext):
        pass


    # Enter a parse tree produced by SapphireParser#mapLiteral.
    def enterMapLiteral(self, ctx:SapphireParser.MapLiteralContext):
        pass

    # Exit a parse tree produced by SapphireParser#mapLiteral.
    def exitMapLiteral(self, ctx:SapphireParser.MapLiteralContext):
        pass


    # Enter a parse tree produced by SapphireParser#mapEntry.
    def enterMapEntry(self, ctx:SapphireParser.MapEntryContext):
        pass

    # Exit a parse tree produced by SapphireParser#mapEntry.
    def exitMapEntry(self, ctx:SapphireParser.MapEntryContext):
        pass


    # Enter a parse tree produced by SapphireParser#structInitializer.
    def enterStructInitializer(self, ctx:SapphireParser.StructInitializerContext):
        pass

    # Exit a parse tree produced by SapphireParser#structInitializer.
    def exitStructInitializer(self, ctx:SapphireParser.StructInitializerContext):
        pass


    # Enter a parse tree produced by SapphireParser#structInitFieldList.
    def enterStructInitFieldList(self, ctx:SapphireParser.StructInitFieldListContext):
        pass

    # Exit a parse tree produced by SapphireParser#structInitFieldList.
    def exitStructInitFieldList(self, ctx:SapphireParser.StructInitFieldListContext):
        pass


    # Enter a parse tree produced by SapphireParser#structInitField.
    def enterStructInitField(self, ctx:SapphireParser.StructInitFieldContext):
        pass

    # Exit a parse tree produced by SapphireParser#structInitField.
    def exitStructInitField(self, ctx:SapphireParser.StructInitFieldContext):
        pass


    # Enter a parse tree produced by SapphireParser#literal.
    def enterLiteral(self, ctx:SapphireParser.LiteralContext):
        pass

    # Exit a parse tree produced by SapphireParser#literal.
    def exitLiteral(self, ctx:SapphireParser.LiteralContext):
        pass


    # Enter a parse tree produced by SapphireParser#arrayLiteral.
    def enterArrayLiteral(self, ctx:SapphireParser.ArrayLiteralContext):
        pass

    # Exit a parse tree produced by SapphireParser#arrayLiteral.
    def exitArrayLiteral(self, ctx:SapphireParser.ArrayLiteralContext):
        pass



del SapphireParser