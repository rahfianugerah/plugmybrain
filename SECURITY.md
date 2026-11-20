# Security Policy

## Supported Versions

| Version | Security fixes |
| :- | :- |
| `main` | <code style="color: green">Supported</code> |
| Any earlier commit | <code style="color: red">Not Supported</code> |

## Reporting a Vulnerability

**Never report a vulnerability in a public issue, a pull request, or a discussion.** Report it privately through GitHub private vulnerability reporting on this repository, under the Security tab, with:

- What the vulnerability is, and where it is.
- The steps to reproduce it.
- The version or commit it affects.
- The impact you expect.

Do not access, change, or delete data that is not yours while testing, and stop as soon as you have shown the issue.

## What Happens Next

| Step | Within |
| :- | :- |
| Acknowledgement of your report | 3 business days |
| An assessment, with a severity | 7 days |
| A fix or a mitigation for a critical or high finding | 30 days |
| A fix for a medium or low finding | The next release |

You are kept informed at every step, and credited in the release notes if you wish.

## Disclosure

Details are published only after a fix is released, or after 90 days, whichever comes first, on a date agreed with you.

## Out of Scope

- A finding that needs physical access to a device, or a device already compromised.
- Social engineering of anyone involved in the project.
- Denial of service by volume.
- A scanner's output with no demonstrated impact.
- Reaching the MCP server or Postgres from another machine after a user rebinds them off `127.0.0.1`. Both bind to loopback by design and carry no authentication of their own.
