"""Shared parsing/filtering/rendering core for the Zscaler firewall feed.

Used by both the AWS Lambda and (in a future phase) the Azure Function
handler, so the IP-handling logic is written and tested once.
"""
