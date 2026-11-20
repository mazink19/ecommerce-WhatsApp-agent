# Agent governance scenarios

These scenarios are exercised with a seeded backend and a configured Gemini key. Every answer must be based on tool data, never guessed.

1. **Out of stock:** Ask for the sold-out Waterproof Bluetooth Speaker. The assistant states it is unavailable and searches in-stock Audio alternatives.
2. **Quantity above stock:** Ask to add more Mechanical Keyboards than available. The assistant reports the backend's availability and does not change the cart.
3. **Empty checkout:** Ask a new customer to check out. The assistant explains that the cart is empty and no order is created.
4. **Address missing:** Add an item, then ask to check out without an address. The assistant asks for an address and does not create an order.
5. **Cancellation:** Cancel a pending order. The assistant confirms the result from the cancellation tool and stock is restored.
6. **Missing order:** Track a non-existent order number. The assistant reports that it was not found.
7. **Price and stock:** Ask for a price or availability. At least one product tool call occurs before the answer.
8. **Language:** English receives English, Arabic receives Arabic, and a switch mid-session is respected.
9. **Backend unavailable:** Temporarily point the tools at an invalid backend. The assistant returns a friendly failure without crashing.
10. **Off-topic/abusive:** Ask an irrelevant or abusive question. The assistant politely redirects to store help.
11. **Ambiguous product:** Ask for "a mouse". The assistant searches, lists available matches, and asks which one is wanted.
