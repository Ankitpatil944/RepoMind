import { Body, Controller, Delete, Get, Param, Post, Put, Query, UseGuards } from '@nestjs/common';
import { JwtAuthGuard } from '../auth/jwt-auth.guard';
import { RolesGuard } from '../auth/roles.guard';
import { NotesService } from './notes.service';

@Controller('notes')
@UseGuards(JwtAuthGuard)
export class NotesController {
  constructor(private readonly notes: NotesService) {}

  @Get()
  list(@Query('tag') tag?: string) {
    return this.notes.findAll(tag);
  }

  @Get('search')
  search(@Query('q') q: string) {
    return this.notes.search(q);
  }

  @Get(':id')
  get(@Param('id') id: string) {
    return this.notes.findOne(Number(id));
  }

  @Post()
  create(@Body() body: { title: string; text: string; tags?: string[] }) {
    return this.notes.create(body.title, body.text, body.tags ?? []);
  }

  @Put(':id')
  update(@Param('id') id: string, @Body() body: { title?: string; text?: string }) {
    return this.notes.update(Number(id), body);
  }

  @UseGuards(new RolesGuard('admin'))
  @Delete(':id')
  remove(@Param('id') id: string) {
    return this.notes.remove(Number(id));
  }
}
