// Synthetic long multilingual passage for layout tests (#274). Written for the tests: no
// real user text, no externally sourced copyrighted passage.
//
// The shared corpus (semant_demo_backend/tests/fixtures/corpus.json) keeps its short texts:
// another document would change the passage, document and chart counts, rankings and corpus
// statistics many tests assert. Browser tests show this passage in place of a fixture
// chunk's text (`useLongPassage` in test/e2e/support.ts); unit tests render it directly.
// Keep it free of leading/trailing whitespace and double spaces: tests compare the rendered
// text exactly.

/** Stable fixture key, for test names and messages. */
export const LONG_PASSAGE_KEY = 'long_multilingual_passage'

/** A word only this passage contains: locate it with `hasText`. */
export const LONG_PASSAGE_TERM = 'Hrnčířovna'

/** An unbreakable token longer than any card is wide. */
export const LONG_PASSAGE_TOKEN = 'https://archiv.example.org/fondy/lhota/kronika-1851/svazek-II/strana-0042/odstavec-0007?zvyrazneni=Hrn%C4%8D%C3%AD%C5%99ovna'

/** The passage: paragraphs separated by a blank line, one hard line break inside one. */
export const LONG_PASSAGE_TEXT = [
  'Roku 1851 zapsal kronikář obce Lhota, že v nové dílně zvané Hrnčířovna u potoka začali pálit ' +
    'džbány, mísy a kachle. Přičinliví tovaryši přišli z Brna, z Jihlavy i ze Žďáru; ' +
    'každý přinesl vlastní zvyky, nářadí a nejneobhospodařovávatelnější pole za humny.',
  'Ein Reisender aus Görlitz schrieb über die Straße nach Prag: „Die Brücke ist schmal, ' +
    'aber die Gastwirtschaft ist groß und gemütlich.“ Pan Łukasz z Wrocławia dodał, ' +
    'że źródło za młynem nigdy nie zamarza.',
  'Seznam zboží podle účetní knihy:\n' +
    '— 12 džbánů po 3 krejcarech; 4 mísy s modrou glazurou; 1 kamna „à la façon de Vienne“.',
  `Odkaz na digitalizovanou stranu: ${LONG_PASSAGE_TOKEN}`,
  // Combining acute (e + U+0301), Cyrillic, Greek and one non-BMP character (U+1F4DC).
  'Poznámka na okraji, psaná jinou rukou: cafe\u0301 u náměstí, Добрый день, καλημέρα ' +
    '— a malý svitek \u{1F4DC} jako značka konce zápisu. Ďakujeme a ťukáme na dvere; ' +
    'ještě dlouho se o Hrnčířovně vyprávělo u kamen, když venku padal sníh.'
].join('\n\n')
