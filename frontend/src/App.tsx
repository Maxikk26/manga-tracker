import { useState } from "react";
import { BookmarkListContainer } from "./containers/BookmarkListContainer";
import { HistoryContainer } from "./containers/HistoryContainer";
import { AppNav, type Screen } from "./components/AppNav";

export function App() {
  const [screen, setScreen] = useState<Screen>("list");

  return (
    <main className="app">
      <header className="app-header">
        <h1>Manga Tracker</h1>
        <AppNav active={screen} onSelect={setScreen} />
      </header>
      {screen === "list" ? <BookmarkListContainer /> : <HistoryContainer />}
    </main>
  );
}
