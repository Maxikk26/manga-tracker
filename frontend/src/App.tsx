import { BookmarkListContainer } from "./containers/BookmarkListContainer";

export function App() {
  return (
    <main className="app">
      <header className="app-header">
        <h1>Manga Tracker</h1>
      </header>
      <BookmarkListContainer />
    </main>
  );
}
