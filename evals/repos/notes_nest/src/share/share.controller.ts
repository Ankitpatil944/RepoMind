import { Controller, Get, Param } from '@nestjs/common';
import { NotesService } from '../notes/notes.service';

/** Read-only public links to a single note; no login needed. */
@Controller('share')
export class ShareController {
  constructor(private readonly notes: NotesService) {}

  @Get(':shareId')
  view(@Param('shareId') shareId: string) {
    return this.notes.findOne(Number(shareId));
  }
}
