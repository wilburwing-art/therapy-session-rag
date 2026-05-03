import { SearchForm } from "./SearchForm";

export const metadata = {
  title: "Search | TherapyRAG",
};

export default function SearchPage() {
  return (
    <div className="space-y-6">
      <header>
        <h1 className="text-2xl font-semibold text-slate-900 sm:text-3xl">Search sessions</h1>
        <p className="mt-1 text-sm text-slate-600">
          Find a past session by transcript, recap, or note content.
        </p>
      </header>
      <SearchForm />
    </div>
  );
}
