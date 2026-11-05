"""Conservative, semantics-preserving, checked-AST optimizations for Caelum."""
from collections import Counter
from dataclasses import fields
from ast_nodes import *
from semantic import Semantic, FunctionInfo


def children(node):
    """Visit source AST fields, never semantic back-pointers or caches."""
    if isinstance(node, ASTNode):
        yield node
        for f in fields(node):
            if f.name not in ('line', 'column'):
                yield from children(getattr(node, f.name))
    elif isinstance(node, (list, tuple)):
        for item in node:
            yield from children(item)


def calls_in(node):
    for part in children(node):
        if isinstance(part, (CallNode, MemberNode)):
            callee = getattr(part, '_callee', None)
            if isinstance(callee, FunctionInfo):
                yield callee
        elif isinstance(part, PipelineNode):
            for stage in part.stages:
                yield stage._callee


def has_effect(expr):
    """Never suppress observable calls, reads, arithmetic traps, or their inputs."""
    if isinstance(expr, (CallNode, PipelineNode, InlineExprNode)):
        return True
    if isinstance(expr, MemberNode) and expr.args is not None:
        return True
    if isinstance(expr, (UnaryNode, BinaryNode)):
        # Nonconstant arithmetic can overflow or divide by zero at runtime.
        if not hasattr(expr, '_constant'):
            return True
    if isinstance(expr, (IntegerLiteralNode, BooleanLiteralNode, StringNode, IdentifierNode)):
        return False
    return any(has_effect(part) for f in fields(expr) if f.name not in ('line', 'column')
               for part in expression_parts(getattr(expr, f.name)))


def expression_parts(value):
    if isinstance(value, ExpressionNode):
        yield value
    elif isinstance(value, (tuple, list)):
        for part in value:
            yield from expression_parts(part)


class Optimizer:
    def __init__(self, program, semantic):
        self.program = program
        self.sem = semantic
        self.serial = 0
        self.used_names = {n.name for n in children(program)
                           if isinstance(n, (IdentifierNode, DeclarationNode, ParameterNode,
                                             FunctionNode, StructNode, FieldNode, CallNode,
                                             PipeStageNode, MemberNode))}

    def recheck(self):
        self.sem = Semantic(self.program).analyze()

    def run(self):
        self.remove_unused_functions()
        self.remove_unused_variables()
        while self.inline_once():
            self.recheck()
            self.remove_unused_functions()
            self.remove_unused_variables()
        self.remove_unused_functions()
        self.remove_unused_variables()
        self.recheck()
        return self.sem

    def remove_unused_functions(self):
        """Mark from executable top-level statements, then remove all unreachable.

        Repeating reachability is the fixed point of ordinary unused-function
        removal, including cascading dependencies and unused methods.
        """
        roots = [n for n in self.program.statements if not isinstance(n, (FunctionNode, StructNode))]
        pending = list(c for n in roots for c in calls_in(n))
        live = set()
        while pending:
            info = pending.pop()
            if info in live:
                continue
            live.add(info)
            pending.extend(info.calls)
        changed = False
        output = []
        for stmt in self.program.statements:
            if isinstance(stmt, FunctionNode) and stmt._info not in live:
                changed = True
                continue
            if isinstance(stmt, StructNode):
                old = len(stmt.methods)
                stmt.methods = [fn for fn in stmt.methods if fn._info in live]
                changed |= len(stmt.methods) != old
            output.append(stmt)
        self.program.statements = output
        if changed:
            self.recheck()
        return changed

    def remove_unused_variables(self):
        while True:
            reads = Counter()
            for part in children(self.program):
                if isinstance(part, IdentifierNode):
                    symbol = getattr(part, '_symbol', None)
                    if symbol is not None:
                        reads[id(symbol)] += 1
            changed = False

            def clean_nested(value):
                if isinstance(value, InlineExprNode):
                    value.statements = clean(value.statements)
                    value.result = clean_nested(value.result)
                elif isinstance(value, ExpressionNode):
                    for f in fields(value):
                        if f.name not in ('line', 'column'):
                            setattr(value, f.name, clean_nested(getattr(value, f.name)))
                elif isinstance(value, list):
                    return [clean_nested(x) for x in value]
                elif isinstance(value, tuple):
                    return tuple(clean_nested(x) for x in value)
                return value

            def clean(body):
                nonlocal changed
                out = []
                for stmt in body:
                    for f in fields(stmt):
                        if f.name not in ('line', 'column') and isinstance(getattr(stmt, f.name), ExpressionNode):
                            setattr(stmt, f.name, clean_nested(getattr(stmt, f.name)))
                    if isinstance(stmt, DeclarationNode) and id(stmt._symbol) not in reads:
                        changed = True
                        if has_effect(stmt.initializer):
                            out.append(CallStatementNode(stmt.line, stmt.column, stmt.initializer))
                        continue
                    if isinstance(stmt, AssignmentNode) and id(stmt._target._symbol) not in reads:
                        changed = True
                        if has_effect(stmt.value):
                            out.append(CallStatementNode(stmt.line, stmt.column, stmt.value))
                        continue
                    if isinstance(stmt, IfNode):
                        stmt.then_body = clean(stmt.then_body)
                        if stmt.else_body is not None:
                            stmt.else_body = clean(stmt.else_body)
                    out.append(stmt)
                return out

            out = []
            for stmt in self.program.statements:
                if isinstance(stmt, FunctionNode):
                    stmt.body = clean(stmt.body)
                    out.append(stmt)
                elif isinstance(stmt, StructNode):
                    for fn in stmt.methods:
                        fn.body = clean(fn.body)
                    out.append(stmt)
                else:
                    out.extend(clean([stmt]))
            self.program.statements = out
            if not changed:
                break
            self.recheck()

    def fresh(self):
        while True:
            i = self.serial
            self.serial += 1
            suffix = ''
            while True:
                suffix = chr(ord('A') + i % 26) + suffix
                i = i // 26 - 1
                if i < 0:
                    break
            name = 'inline' + suffix
            if name not in self.used_names:
                self.used_names.add(name)
                return name

    @staticmethod
    def supported(info):
        """Straight-line global functions with a final rise; no global capture."""
        if info.owner or not info.node.body or not isinstance(info.node.body[-1], ReturnNode):
            return False
        if any(not isinstance(n, (DeclarationNode, AssignmentNode)) for n in info.node.body[:-1]):
            return False
        for stmt in info.node.body:
            if isinstance(stmt, AssignmentNode):
                if stmt._target._symbol.kind not in ('local', 'parameter'):
                    return False
            for n in children(stmt):
                if isinstance(n, (CallNode, PipelineNode, InlineExprNode)):
                    return False
                if isinstance(n, MemberNode) and n.args is not None:
                    return False
                if isinstance(n, IdentifierNode):
                    symbol = getattr(n, '_symbol', None)
                    if symbol is not None and symbol.kind not in ('local', 'parameter'):
                        return False
        return True

    def inline_once(self):
        counts = Counter(c for c in calls_in(self.program))
        def recursive(start):
            todo = list(start.calls)
            seen = set()
            while todo:
                info = todo.pop()
                if info is start:
                    return True
                if info not in seen:
                    seen.add(info)
                    todo.extend(info.calls)
            return False

        eligible = {f for f, count in counts.items()
                    if count == 1 and self.supported(f) and not recursive(f)}
        if not eligible:
            return False
        target = next(f for f in self.sem.functions.values() if f in eligible)
        done = False

        def rewrite_expr(n):
            nonlocal done
            if isinstance(n, PipelineNode):
                n.value = rewrite_expr(n.value)
                if any(stage._callee is target for stage in n.stages):
                    result = n.value
                    for stage in n.stages:
                        result = CallNode(stage.line, stage.column, stage.name, [result])
                        if stage._callee is target and not done:
                            result = self.expand(result, target)
                            done = True
                    return result
                return n
            if isinstance(n, CallNode):
                n.args = [rewrite_expr(x) for x in n.args]
                if getattr(n, '_callee', None) is target and not done:
                    done = True
                    return self.expand(n, target)
                return n
            # Rebuild nested expressions in source-field order. This does not
            # reorder evaluation and leaves function/method names untouched.
            for f in fields(n):
                if f.name not in ('line', 'column'):
                    v = getattr(n, f.name)
                    setattr(n, f.name, rewrite_value(v))
            return n

        def rewrite_value(v):
            if isinstance(v, ExpressionNode):
                return rewrite_expr(v)
            if isinstance(v, list):
                return [rewrite_value(x) for x in v]
            if isinstance(v, tuple):
                return tuple(rewrite_value(x) for x in v)
            return v

        def rewrite_stmt(n):
            for f in fields(n):
                if f.name in ('line', 'column'):
                    continue
                v = getattr(n, f.name)
                if isinstance(v, ExpressionNode) or isinstance(v, (list, tuple)):
                    setattr(n, f.name, rewrite_container(v))

        def rewrite_container(v):
            if isinstance(v, ExpressionNode):
                return rewrite_expr(v)
            if isinstance(v, StatementNode):
                rewrite_stmt(v)
                return v
            if isinstance(v, list):
                return [rewrite_container(x) for x in v]
            if isinstance(v, tuple):
                return tuple(rewrite_container(x) for x in v)
            return v

        # Top-level execution first, followed by reachable function bodies.
        for stmt in self.program.statements:
            if not isinstance(stmt, (StructNode, FunctionNode)):
                rewrite_stmt(stmt)
                if done:
                    return True
        for stmt in self.program.statements:
            if isinstance(stmt, FunctionNode):
                for s in stmt.body:
                    rewrite_stmt(s)
                    if done:
                        return True
            if isinstance(stmt, StructNode):
                for fn in stmt.methods:
                    for s in fn.body:
                        rewrite_stmt(s)
                        if done:
                            return True
        return False

    def expand(self, call, info):
        """Replace the call with scoped parameter bindings + copied body + value."""
        replacements = {}
        for param in info.node.parameters:
            replacements[id(param)] = self.fresh()
        for stmt in info.node.body:
            for part in children(stmt):
                if isinstance(part, DeclarationNode):
                    replacements[id(part)] = self.fresh()

        def renamed_copy(original):
            if isinstance(original, ASTNode):
                result = type(original)(**{f.name: renamed_copy(getattr(original, f.name)) for f in fields(original)})
                if isinstance(original, DeclarationNode):
                    result.name = replacements[id(original)]
                if isinstance(original, IdentifierNode):
                    symbol = getattr(original, '_symbol', None)
                    if symbol is not None and symbol.node is not None:
                        result.name = replacements.get(id(symbol.node), result.name)
                if isinstance(original, AssignmentNode):
                    symbol = original._target._symbol
                    result.name = replacements.get(id(symbol.node), result.name)
                return result
            if isinstance(original, list):
                return [renamed_copy(x) for x in original]
            if isinstance(original, tuple):
                return tuple(renamed_copy(x) for x in original)
            return original

        bindings = [DeclarationNode(p.line, p.column, 'flow' if p.mutable else 'calm',
                                    p.type_name, replacements[id(p)], arg)
                    for p, arg in zip(info.node.parameters, call.args)]
        body = [renamed_copy(stmt) for stmt in info.node.body[:-1]]
        result = renamed_copy(info.node.body[-1].value)
        return InlineExprNode(call.line, call.column, bindings + body, result, info.result)
