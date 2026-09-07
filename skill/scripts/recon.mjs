// recon.mjs — kalibreringsläge: dumpar page-struktur, navigering och fulltext.
const btns = [...document.querySelectorAll('a, button, [role="tab"], [role="menuitem"]')]
  .map((e) => (e.innerText || '').replace(/\s+/g, ' ').trim())
  .filter((t) => t && t.length < 40 && !t.startsWith('http'));
const uniq = [...new Set(btns)];

return {
  url: location.href,
  title: document.title,
  loggedInGuess: !/logga in|bankid|inloggning/i.test(document.body.innerText.slice(0, 2000)),
  nav: uniq.slice(0, 80),
  text: (document.body.innerText || '').replace(/\n{3,}/g, '\n\n').slice(0, 16000),
};
