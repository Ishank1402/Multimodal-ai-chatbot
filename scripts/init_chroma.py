"""
scripts/init_chroma.py
───────────────────────
Seed the ChromaDB collection with FAQ / knowledge-base documents.
Edit the FAQ_DATA list below with your own content, then run:

    python scripts/init_chroma.py

ChromaDB must be running (docker-compose up chromadb) before executing this.
"""

import sys
from pathlib import Path

sys.path.insert(0, str(Path(__file__).parent.parent))

from app.storage.vector_store import load_faq_documents
from app.config import settings

# =============================================================================
# ✏️  EDIT THIS LIST — add your own FAQs / knowledge-base entries below
# =============================================================================
FAQ_DATA = [
    {
        "id": "faq_001",
        "document": (
            "What are your business hours? "
            "We are open Monday to Friday, 9 AM to 6 PM (IST). "
            "On weekends we operate from 10 AM to 2 PM."
        ),
        "metadata": {"category": "general", "source": "faq"},
    },
    {
        "id": "faq_002",
        "document": (
            "How do I track my order? "
            "You can track your order by visiting our website and entering your "
            "order ID in the 'Track Order' section. You will also receive an "
            "email with a tracking link once your order is shipped."
        ),
        "metadata": {"category": "orders", "source": "faq"},
    },
    {
        "id": "faq_003",
        "document": (
            "What is your return policy? "
            "We offer a 30-day hassle-free return policy on all products. "
            "Items must be unused and in original packaging. "
            "Contact support@example.com to initiate a return."
        ),
        "metadata": {"category": "returns", "source": "faq"},
    },
    {
        "id": "faq_004",
        "document": (
            "How can I contact customer support? "
            "You can reach us via email at support@example.com, "
            "call us at +91-XXXXXXXXXX, or chat with us on Telegram. "
            "Response time is typically within 2 business hours."
        ),
        "metadata": {"category": "support", "source": "faq"},
    },
    {
        "id": "faq_005",
        "document": (
            "What payment methods do you accept? "
            "We accept credit/debit cards (Visa, Mastercard, Amex), "
            "UPI (Google Pay, PhonePe, Paytm), Net Banking, and EMI options."
        ),
        "metadata": {"category": "payments", "source": "faq"},
    },
    {
        "id": "faq_006",
        "document": (
            "Is my personal data safe with you? "
            "Yes. We follow GDPR and India IT Act guidelines. Your data is "
            "encrypted at rest and in transit. We never sell your data to third parties."
        ),
        "metadata": {"category": "privacy", "source": "faq"},
    },
    # ── Add more entries here ──────────────────────────────────────────────
]


def main():
    print(f"[init_chroma] Target collection: {settings.chroma_collection_name}")
    print(f"[init_chroma] ChromaDB at: {settings.chroma_host}:{settings.chroma_port}")
    n = load_faq_documents(FAQ_DATA)
    print(f"[init_chroma] ✅  Upserted {n} documents into '{settings.chroma_collection_name}'")


if __name__ == "__main__":
    main()
