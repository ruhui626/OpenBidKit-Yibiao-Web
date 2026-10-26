// Exercises the unchanged production parser on synthetic files only.
import fs from 'node:fs/promises';
import path from 'node:path';
import { pathToFileURL } from 'node:url';

const [repo, fixtureDir, outputFile, ...sourceNames] = process.argv.slice(2);
if (!repo || !fixtureDir || !outputFile) throw new Error('Expected repo, fixture directory, output file');
const reports = [];
let parser;
try {
  parser = await import(pathToFileURL(path.join(repo, 'server/src/document/parser.ts')).href);
} catch (error) {
  reports.push({ stage: 'module-import', ok: false, error: String(error?.message ?? error) });
}
if (parser) {
  for (const name of sourceNames.length ? sourceNames : ['before.docx', 'after.docx', 'edges.docx']) {
    try {
      const result = await parser.parseDocument(path.join(fixtureDir, name));
      reports.push({ sourceName: name, ok: true, fields: Object.keys(result), ...result });
    } catch (error) {
      reports.push({ sourceName: name, ok: false, error: String(error?.message ?? error) });
    }
  }
}
await fs.writeFile(outputFile, JSON.stringify({ synthetic: true, reports }, null, 2), 'utf8');
console.log(JSON.stringify({ files: reports.length, ok: reports.filter(r => r.ok).length }));
