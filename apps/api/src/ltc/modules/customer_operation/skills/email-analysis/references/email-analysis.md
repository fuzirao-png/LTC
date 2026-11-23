# Inbound Email Classification

Use deterministic parsing first for delivery notifications. Chinese mailbox-provider notifications may identify the original recipient with phrases such as `无法发送到 address` or `收件人（address）`, the original subject with `主 题：...`, and SMTP status with codes such as `550 5.4.1`.

Automatic replies count as replies but remain separately categorized. Customer replies use the reply-intent classifier. Unknown provider notices must be retained without changing delivery state unless reliable evidence identifies the original outbound email and status.
