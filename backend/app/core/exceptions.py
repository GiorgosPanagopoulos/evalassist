"""Domain-level exceptions.

Μόνο ορισμοί εδώ· το mapping σε HTTP status codes γίνεται στο API layer
(Φάση 4), όχι εδώ.
"""


class NotFoundError(Exception):
    """Το ζητούμενο resource (person/evaluation/document) δεν βρέθηκε."""


class IsolationError(Exception):
    """Παραβίαση ή αδυναμία επιβολής του isolation scope σε ένα query."""


class LLMUnavailableError(Exception):
    """Το τοπικό LLM (Ollama) δεν είναι διαθέσιμο ή επέστρεψε σφάλμα."""
