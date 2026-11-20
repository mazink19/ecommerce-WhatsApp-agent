## Behavior

The agent uses live backend tools before stating prices, stock, cart contents, order totals, or order status. It keeps one Gemini chat and one cart identity per WhatsApp number. It can handle a compound request in one turn, searches Arabic transliterations against the English catalog, requests a shipping address before checkout, and explains inventory, empty-cart, unavailable-backend, and not-found failures without inventing data. Full repeatable scenario expectations are in `tests/scenarios.md`.
