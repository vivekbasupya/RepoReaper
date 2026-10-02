import { DiffEditor, loader } from '@monaco-editor/react';
import * as monaco from 'monaco-editor';
import editorWorker from 'monaco-editor/esm/vs/editor/editor.worker?worker';
(self as typeof self & {MonacoEnvironment: {getWorker: () => Worker}}).MonacoEnvironment = { getWorker: () => new editorWorker() };
loader.config({ monaco });
export default function Diff({ original, modified, language, light }: {original: string; modified: string; language: string; light: boolean}) {
  return <DiffEditor height="320px" language={language} original={original} modified={modified} theme={light ? 'vs' : 'vs-dark'} options={{ readOnly: true, originalEditable: false, minimap: {enabled: false}, renderSideBySide: window.innerWidth > 768, scrollBeyondLastLine: false, fontSize: 13, padding: {top: 20}, accessibilitySupport: 'on' }}/>;
}
