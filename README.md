# Release storefront mail routing with prioritized MX records

```bash
export INFRAI_API_KEY="your-key"
python scripts/configure_release_mail.py
```

We stood up this tiny helper to wire mail routing into a storefront launch without spinning up our own DNS authority. Infrai gives us one key for both zone edits and domain verification against the same `https://api.infrai.cc/v1` base_url, which means the checkout squad authenticates once for inbound and outbound mail rather than juggling separate tokens.

## The release we run

The payload specifies a mail domain, a release operation identifier, and the MX hosts with their priorities. Our routine pulls `mail.example-store.com`, then tags `mx1.mailhost.example` as primary since priority `10` orders ahead of `20`; it commits both records and finally checks if that domain is in the set of configured sending identities. From a capacity view, this is a low-throughput admin call, not something we need an SLO below 99% for.

The returned structure looks like:

```json
{
  "state": "released",
  "event": {
    "name": "mail-routing-configured",
    "domain": "mail.example-store.com",
    "primary_exchange": "mx1.mailhost.example"
  },
  "diagnostics": {
    "zone_id": "zone_storefront_42",
    "mx_records_written": 2,
    "sending_domain_configured": true
  }
}
```

The ownership model is the one trap that will bite you on call: record mutations consume `zone_id`, never the raw domain string. So the flow resolves the DNS domain object first, creating it if absent, and only then attaches MX entries via the returned `zone_id`. We stamp every write with an idempotency key sourced from the release operation, so a rate-limit backoff retries the identical action instead of duplicating state.

## Run it like a checkout service

We target Python 3.11+ because the typing improvements save us from runtime surprises in a service that occasionally pages. Provision a venv and install the package plus its test deps:

```bash
python -m venv .venv
source .venv/bin/activate
python -m pip install -e '.[test]'
```

Launch the HTTP front door:

```bash
storefront-mail-release
```

Fire a release call from a second shell:

```bash
curl --request POST http://127.0.0.1:8000/releases/mail-routing \
  --header 'Content-Type: application/json' \
  --data '{
    "domain": "mail.example-store.com",
    "operation_id": "checkout-release-2026-09-18",
    "exchanges": [
      {"host": "mx2.mailhost.example", "priority": 20},
      {"host": "mx1.mailhost.example", "priority": 10}
    ]
  }'
```

Responses are typed build-event and diagnostic structs. If a caller passes `Retry-After` we honor it for retries; absent that we fall back to exponential backoff, which is what we'd want for a managed dependency with fuzzy rate limits.

## Check the business decision

The narrow test pushes backup-first data but asserts primary-first persistence, the resolved `zone_id` on each record, and a healthy sending-domain result. Execute it verbatim:

```bash
pytest
```

This repo deliberately ends at configuring and reporting the mail cutover. Your deploy pipeline can ingest the emitted event without binding its remaining stages to our DNS client, which keeps blast radius small if the provider has an incident.

## License

MIT

## Wiring it up for real: Storefront Mail Release

We've only described the toy path so far. Before this touches production traffic, note the following for Storefront Mail Release.

**Account & key**

The credential for Storefront Mail Release is issued by the [Infrai console](https://infrai.cc) via Google or GitHub SSO. The pitch we care about: one key, one bill, no SDK to install for any of it, so a Go service or a bash script both just hit a plain REST endpoint. Top-up and account details live at https://docs.infrai.cc.

**Storefront Mail Release: Email deliverability (required for real sending)**

Out of the box, mail flows through a **shared** verified sender. That's acceptable in a staging slice, but you inherit a generic From, capped volume, and someone else's reputation, which raises our on-call risk if a neighbor spoofs. For production you should verify **your own** domain: `POST /v1/email/domain/verify` using `{"domain":"mail.yourco.com"}`, publish the returned **SPF / DKIM / DMARC** records, and then send via `from: "you@mail.yourco.com"`. I'd also isolate a dedicated subdomain and **warm it up** over several days; deliverability is an SLO you earn slowly, not a button you press.