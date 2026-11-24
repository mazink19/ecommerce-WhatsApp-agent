import logging
import sys

from neonize.client import NewClient
from neonize.events import ConnectedEv, MessageEv
from neonize.utils import extract_text

import agent

logging.basicConfig(
    level=logging.INFO,
    format="%(asctime)s | %(levelname)s | %(message)s",
)

logger = logging.getLogger(__name__)

# Persistent WhatsApp authentication/session state.
client = NewClient("store-bot")


@client.event(ConnectedEv)
def on_connected(_: NewClient, __: ConnectedEv) -> None:
    logger.info("WhatsApp connected successfully.")


@client.event(MessageEv)
def on_message(client: NewClient, message: MessageEv) -> None:
    source = message.Info.MessageSource

    # Ignore messages sent by this bot and group messages.
    if source.IsFromMe or source.IsGroup:
        return

    chat_jid = source.Chat
    phone = chat_jid.User
    incoming_text = extract_text(message.Message).strip()

    if not phone or not incoming_text:
        return

    logger.info("Incoming message from %s", phone)

    try:
        response = agent.handle_message(phone, incoming_text)

        if response:
            client.send_message(chat_jid, response)
            logger.info("Reply sent to %s", phone)

    except Exception:
        logger.exception("Failed to process message from %s", phone)

        try:
            client.send_message(
                chat_jid,
                "Sorry, something went wrong. Please try again.",
            )
        except Exception:
            logger.exception("Failed to send error reply to %s", phone)


def main() -> None:
    # Neonize displays its QR code in the terminal by default.
    logger.info("Starting WhatsApp bot...")
    logger.info("Scan the QR code with WhatsApp if pairing is required.")

    try:
        client.connect()
    except KeyboardInterrupt:
        logger.info("Shutdown requested.")
    except Exception:
        logger.exception("WhatsApp connection failed.")
        sys.exit(1)
    finally:
        client.stop()
        logger.info("WhatsApp bot stopped.")


if __name__ == "__main__":
    main()
