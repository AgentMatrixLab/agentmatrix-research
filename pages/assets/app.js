const searchInput = document.getElementById("module-search");
const moduleCards = Array.from(document.querySelectorAll("#module-grid .content-card"));

function normalizeText(value) {
  return value.trim().toLowerCase();
}

function filterModules() {
  const keyword = normalizeText(searchInput.value);
  moduleCards.forEach((card) => {
    const haystack = normalizeText(card.textContent + " " + (card.dataset.keywords || ""));
    const matched = keyword === "" || haystack.includes(keyword);
    card.classList.toggle("is-hidden", !matched);
  });
}

if (searchInput) {
  searchInput.addEventListener("input", filterModules);
}
