export interface Note {
  id: number;
  title: string;
  text: string;
  tags: string[];
  createdAt: Date;
}

const notes: Note[] = [];
let nextId = 1;

export class NotesService {
  findAll(tag?: string): Note[] {
    return tag ? notes.filter((n) => n.tags.includes(tag)) : notes;
  }

  findOne(id: number): Note {
    const note = notes.find((n) => n.id === id);
    if (!note) throw new Error(`note ${id} not found`);
    return note;
  }

  /** Case-insensitive substring search over title and text. */
  search(query: string): Note[] {
    const q = query.toLowerCase();
    return notes.filter((n) => n.title.toLowerCase().includes(q) || n.text.toLowerCase().includes(q));
  }

  create(title: string, text: string, tags: string[]): Note {
    const note: Note = { id: nextId++, title, text, tags, createdAt: new Date() };
    notes.push(note);
    return note;
  }

  update(id: number, patch: { title?: string; text?: string }): Note {
    const note = this.findOne(id);
    Object.assign(note, patch);
    return note;
  }

  remove(id: number): { removed: boolean } {
    const index = notes.findIndex((n) => n.id === id);
    if (index >= 0) notes.splice(index, 1);
    return { removed: index >= 0 };
  }
}
