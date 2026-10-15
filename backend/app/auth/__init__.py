"""Login με username/password, sessions και διαχείριση χρηστών.

Αντικαθιστά ολοκληρωτικά το (spoofable) X-User header: ο χρήστης κάθε
request προκύπτει ΜΟΝΟ από το session cookie (βλ. app.auth.deps)."""
