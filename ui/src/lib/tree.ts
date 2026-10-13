import type { FileEntry } from '../api/types'

export interface TreeNode {
  name: string
  path: string
  kind: 'dir' | 'file'
  children: TreeNode[]
  file?: FileEntry
  /** files under a directory (or 1 for a file) */
  fileCount: number
  /** endpoints defined under this node */
  endpoints: number
}

/** Build a directory tree from flat file paths; directories sort before files. */
export function buildFileTree(files: FileEntry[]): TreeNode {
  const root: TreeNode = { name: '', path: '', kind: 'dir', children: [], fileCount: 0, endpoints: 0 }
  for (const file of files) {
    const parts = file.path.split('/')
    let node = root
    parts.forEach((part, i) => {
      const isFile = i === parts.length - 1
      const path = parts.slice(0, i + 1).join('/')
      let child = node.children.find((c) => c.name === part && c.kind === (isFile ? 'file' : 'dir'))
      if (!child) {
        child = {
          name: part,
          path,
          kind: isFile ? 'file' : 'dir',
          children: [],
          fileCount: 0,
          endpoints: 0,
          file: isFile ? file : undefined,
        }
        node.children.push(child)
      }
      child.fileCount += 1
      child.endpoints += file.endpoints
      node = child
    })
    root.fileCount += 1
    root.endpoints += file.endpoints
  }
  const sort = (n: TreeNode) => {
    n.children.sort((a, b) =>
      a.kind === b.kind ? a.name.localeCompare(b.name) : a.kind === 'dir' ? -1 : 1,
    )
    n.children.forEach(sort)
  }
  sort(root)
  return root
}

export interface VisibleRow {
  node: TreeNode
  depth: number
}

/** Rows to render, honouring which directories are expanded. */
export function flattenVisible(root: TreeNode, expanded: ReadonlySet<string>): VisibleRow[] {
  const rows: VisibleRow[] = []
  const walk = (n: TreeNode, depth: number) => {
    for (const child of n.children) {
      rows.push({ node: child, depth })
      if (child.kind === 'dir' && expanded.has(child.path)) walk(child, depth + 1)
    }
  }
  walk(root, 0)
  return rows
}

/** Every ancestor directory of a path, e.g. "a/b/c.py" -> ["a", "a/b"]. */
export function ancestors(path: string): string[] {
  const parts = path.split('/')
  return parts.slice(0, -1).map((_, i) => parts.slice(0, i + 1).join('/'))
}
