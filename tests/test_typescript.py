from app.ingest.analysis import analyze_source
from app.ingest.parser import parse_source

NEST = b"""
import { Controller, Get, Post, UseGuards, Body } from '@nestjs/common';
import { UsersService } from './users.service';

@Controller('users')
@UseGuards(JwtAuthGuard)
export class UsersController {
  constructor(private readonly svc: UsersService) {}

  @Get(':id')
  async findOne(id: string): Promise<User> {
    return this.svc.find(id);
  }

  @Post()
  @UseGuards(RolesGuard)
  create(@Body() dto: CreateDto) {
    return this.svc.create(dto);
  }
}

@Controller('auth')
export class AuthController {
  @Post('login')
  login(dto: LoginDto) { return jwt.sign(dto); }
}
"""

EXPRESS_TS = b"""
import express, { Request, Response } from 'express';
import { requireAuth } from './middleware/auth';

const app = express();
interface Item { id: number }

app.get('/health', (req: Request, res: Response) => res.json({ ok: true }));
app.post('/items', requireAuth, createItem);

export async function createItem(req: Request, res: Response): Promise<void> {
  const item: Item = { id: 1 };
  res.json(item);
}
"""

TSX = b"""
import React from 'react';
export function Hello({ name }: { name: string }) {
  return <div className="x">{name}</div>;
}
"""


def test_typescript_chunks_have_signatures_and_kinds():
    chunks = {c.qualified_name: c for c in parse_source(EXPRESS_TS, "typescript")}
    assert chunks["createItem"].kind == "function"
    assert "createItem" in chunks["createItem"].signature


def test_tsx_falls_back_to_the_jsx_grammar():
    names = [c.name for c in parse_source(TSX, "typescript")]
    assert "Hello" in names


def test_nest_controller_routes():
    eps = {(e.method, e.path): e for e in analyze_source(NEST, "typescript").endpoints}
    assert set(eps) == {("GET", "/users/:id"), ("POST", "/users"), ("POST", "/auth/login")}

    find = eps[("GET", "/users/:id")]
    assert find.framework == "nestjs"
    assert find.handler_name == "findOne"
    assert "JwtAuthGuard" in find.signals  # class-level guard applies to every route

    create = eps[("POST", "/users")]
    assert {"JwtAuthGuard", "RolesGuard"} <= set(create.signals)

    assert eps[("POST", "/auth/login")].signals == ()


def test_nest_handler_line_matches_the_method_chunk():
    analysis = analyze_source(NEST, "typescript")
    starts = {c.name: c.start_line for c in parse_source(NEST, "typescript") if c.kind in ("function", "method")}
    for e in analysis.endpoints:
        assert e.handler_line == starts[e.handler_name]


def test_express_routes_work_in_typescript():
    eps = {(e.method, e.path): e for e in analyze_source(EXPRESS_TS, "typescript").endpoints}
    assert set(eps) == {("GET", "/health"), ("POST", "/items")}
    assert eps[("POST", "/items")].signals == ("requireAuth",)
    assert eps[("POST", "/items")].handler_name == "createItem"
    assert eps[("POST", "/items")].framework == "express"


def test_ts_imports_are_collected():
    imports = analyze_source(NEST, "typescript").imports
    assert "@nestjs/common" in imports and "./users.service" in imports
