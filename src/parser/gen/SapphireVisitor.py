# Generated from grammar/Sapphire.g4 by ANTLR 4.13.2
from antlr4 import *
if "." in __name__:
    from .SapphireParser import SapphireParser
else:
    from SapphireParser import SapphireParser

# This class defines a complete generic visitor for a parse tree produced by SapphireParser.

class SapphireVisitor(ParseTreeVisitor):

    # Visit a parse tree produced by SapphireParser#program.
    def visitProgram(self, ctx:SapphireParser.ProgramContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#topLevelItem.
    def visitTopLevelItem(self, ctx:SapphireParser.TopLevelItemContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#importStatement.
    def visitImportStatement(self, ctx:SapphireParser.ImportStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#exportStatement.
    def visitExportStatement(self, ctx:SapphireParser.ExportStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#exportSpecifier.
    def visitExportSpecifier(self, ctx:SapphireParser.ExportSpecifierContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#identifierPath.
    def visitIdentifierPath(self, ctx:SapphireParser.IdentifierPathContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#annotation.
    def visitAnnotation(self, ctx:SapphireParser.AnnotationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#declaration.
    def visitDeclaration(self, ctx:SapphireParser.DeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#enumDeclaration.
    def visitEnumDeclaration(self, ctx:SapphireParser.EnumDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#enumMember.
    def visitEnumMember(self, ctx:SapphireParser.EnumMemberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#typeParamList.
    def visitTypeParamList(self, ctx:SapphireParser.TypeParamListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#typeArgumentList.
    def visitTypeArgumentList(self, ctx:SapphireParser.TypeArgumentListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#structDeclaration.
    def visitStructDeclaration(self, ctx:SapphireParser.StructDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#structField.
    def visitStructField(self, ctx:SapphireParser.StructFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#implBlock.
    def visitImplBlock(self, ctx:SapphireParser.ImplBlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#implMember.
    def visitImplMember(self, ctx:SapphireParser.ImplMemberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#traitDeclaration.
    def visitTraitDeclaration(self, ctx:SapphireParser.TraitDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#returnTypeList.
    def visitReturnTypeList(self, ctx:SapphireParser.ReturnTypeListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#traitMember.
    def visitTraitMember(self, ctx:SapphireParser.TraitMemberContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#functionDeclaration.
    def visitFunctionDeclaration(self, ctx:SapphireParser.FunctionDeclarationContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#baseInitializerList.
    def visitBaseInitializerList(self, ctx:SapphireParser.BaseInitializerListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#baseInitializer.
    def visitBaseInitializer(self, ctx:SapphireParser.BaseInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#functionName.
    def visitFunctionName(self, ctx:SapphireParser.FunctionNameContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#parameterList.
    def visitParameterList(self, ctx:SapphireParser.ParameterListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#parameter.
    def visitParameter(self, ctx:SapphireParser.ParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#type.
    def visitType(self, ctx:SapphireParser.TypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#collectionType.
    def visitCollectionType(self, ctx:SapphireParser.CollectionTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#baseType.
    def visitBaseType(self, ctx:SapphireParser.BaseTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#functionType.
    def visitFunctionType(self, ctx:SapphireParser.FunctionTypeContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#statement.
    def visitStatement(self, ctx:SapphireParser.StatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#matchStatement.
    def visitMatchStatement(self, ctx:SapphireParser.MatchStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#breakStatement.
    def visitBreakStatement(self, ctx:SapphireParser.BreakStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#continueStatement.
    def visitContinueStatement(self, ctx:SapphireParser.ContinueStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#yieldStatement.
    def visitYieldStatement(self, ctx:SapphireParser.YieldStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#matchExpression.
    def visitMatchExpression(self, ctx:SapphireParser.MatchExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#matchCase.
    def visitMatchCase(self, ctx:SapphireParser.MatchCaseContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#matchPattern.
    def visitMatchPattern(self, ctx:SapphireParser.MatchPatternContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#block.
    def visitBlock(self, ctx:SapphireParser.BlockContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#varBinding.
    def visitVarBinding(self, ctx:SapphireParser.VarBindingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#varBindingList.
    def visitVarBindingList(self, ctx:SapphireParser.VarBindingListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#expressionList.
    def visitExpressionList(self, ctx:SapphireParser.ExpressionListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#variableDeclarationStatement.
    def visitVariableDeclarationStatement(self, ctx:SapphireParser.VariableDeclarationStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#targetList.
    def visitTargetList(self, ctx:SapphireParser.TargetListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#assignmentStatement.
    def visitAssignmentStatement(self, ctx:SapphireParser.AssignmentStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#expressionStatement.
    def visitExpressionStatement(self, ctx:SapphireParser.ExpressionStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#returnStatement.
    def visitReturnStatement(self, ctx:SapphireParser.ReturnStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#ifStatement.
    def visitIfStatement(self, ctx:SapphireParser.IfStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#guardStatement.
    def visitGuardStatement(self, ctx:SapphireParser.GuardStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#whileStatement.
    def visitWhileStatement(self, ctx:SapphireParser.WhileStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#letOrVarBinding.
    def visitLetOrVarBinding(self, ctx:SapphireParser.LetOrVarBindingContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#forStatement.
    def visitForStatement(self, ctx:SapphireParser.ForStatementContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#CoalesceExpr.
    def visitCoalesceExpr(self, ctx:SapphireParser.CoalesceExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#LambdaExpr.
    def visitLambdaExpr(self, ctx:SapphireParser.LambdaExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#UnaryExpr.
    def visitUnaryExpr(self, ctx:SapphireParser.UnaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#LogicalAndExpr.
    def visitLogicalAndExpr(self, ctx:SapphireParser.LogicalAndExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#IndexExpr.
    def visitIndexExpr(self, ctx:SapphireParser.IndexExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#MultiplicativeExpr.
    def visitMultiplicativeExpr(self, ctx:SapphireParser.MultiplicativeExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#LogicalOrExpr.
    def visitLogicalOrExpr(self, ctx:SapphireParser.LogicalOrExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#CloneExpr.
    def visitCloneExpr(self, ctx:SapphireParser.CloneExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#AdditiveExpr.
    def visitAdditiveExpr(self, ctx:SapphireParser.AdditiveExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#CompareExpr.
    def visitCompareExpr(self, ctx:SapphireParser.CompareExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#CastExpr.
    def visitCastExpr(self, ctx:SapphireParser.CastExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#PrimaryExpr.
    def visitPrimaryExpr(self, ctx:SapphireParser.PrimaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#CallExpr.
    def visitCallExpr(self, ctx:SapphireParser.CallExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#MoveExpr.
    def visitMoveExpr(self, ctx:SapphireParser.MoveExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#MemberAccessExpr.
    def visitMemberAccessExpr(self, ctx:SapphireParser.MemberAccessExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#TernaryExpr.
    def visitTernaryExpr(self, ctx:SapphireParser.TernaryExprContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#lambdaExpression.
    def visitLambdaExpression(self, ctx:SapphireParser.LambdaExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#lambdaParameters.
    def visitLambdaParameters(self, ctx:SapphireParser.LambdaParametersContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#lambdaParameter.
    def visitLambdaParameter(self, ctx:SapphireParser.LambdaParameterContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#argumentList.
    def visitArgumentList(self, ctx:SapphireParser.ArgumentListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#argument.
    def visitArgument(self, ctx:SapphireParser.ArgumentContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#memberAccess.
    def visitMemberAccess(self, ctx:SapphireParser.MemberAccessContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#primaryExpression.
    def visitPrimaryExpression(self, ctx:SapphireParser.PrimaryExpressionContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#mapLiteral.
    def visitMapLiteral(self, ctx:SapphireParser.MapLiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#mapEntry.
    def visitMapEntry(self, ctx:SapphireParser.MapEntryContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#structInitializer.
    def visitStructInitializer(self, ctx:SapphireParser.StructInitializerContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#structInitFieldList.
    def visitStructInitFieldList(self, ctx:SapphireParser.StructInitFieldListContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#structInitField.
    def visitStructInitField(self, ctx:SapphireParser.StructInitFieldContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#literal.
    def visitLiteral(self, ctx:SapphireParser.LiteralContext):
        return self.visitChildren(ctx)


    # Visit a parse tree produced by SapphireParser#arrayLiteral.
    def visitArrayLiteral(self, ctx:SapphireParser.ArrayLiteralContext):
        return self.visitChildren(ctx)



del SapphireParser