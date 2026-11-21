export function AICommandSuggestion({ id, onSelect }: { id: string; onSelect: () => void }) {
  return <div id={id} className="ai-command-menu" role="listbox" aria-label="Gợi ý lệnh">
    <button type="button" role="option" aria-selected="true" onMouseDown={event => event.preventDefault()} onClick={onSelect}>
      <span className="ai-command-chip">AI</span>
      <span>Tìm tài liệu trong thư viện</span>
      <kbd>↵</kbd>
    </button>
  </div>
}
