---
layout: post
title: "Physical Touch as Proof of Human Approval"
date: 2026-02-06
---

As AI coding agents become more capable and write all the code and all the documents, it's not clear how to know what has been human approved.

The other day I was looking into whether or not there was a way to have Claude Code affix my signature to a PDF because I was feeling too lazy to upload it to DocuSign and sign it. At some point, I had some interesting insight that I was trying to fully have the computer forge my signature, and this felt like a bridge too far.

But it's a very interesting question of how we could credibly show that I, Ben, have reviewed a document or an email and have approved it. This goes back to all the cool crypto stuff that got us excited about Bitcoin in the first place.

I've been experimenting with a workflow that uses cryptographic signatures to create a clear, verifiable distinction between "agent generated code on my behalf" and "human approved this."

## The Core Idea

The workflow is simple:

1. An AI agent (like Claude Code) writes code and commits freely to feature branches
2. These commits are **unsigned** - they represent work submitted for review
3. When I'm ready to approve I can create a **signed merge commit** to main
4. The signature requires my physical touch on a biometric sensor (Touch ID or YubiKey)
5. GitHub enforces that only signed commits can land on protected branches

The signature is then proof of a physical human presence, or at least some being with a finger.

It seems like a generally important norm to establish for all kinds of workflows, as we have more and more agents running on our behalf, we need ways to create 'chains of responsibility'. When I have an AI agent negotiate for my next car, I should still be the one who's saying yes, I approve of the extra sunroof features.

## Technical Explanation

I'm using macOS's Secure Enclave via an app called [Secretive](https://github.com/maxgoedjen/secretive).

* The private signing key is generated inside the Secure Enclave, which is a separate security chip.
* The key never leaves the hardware, and it cannot be extracted, even with root access
* Every signature requires a fresh Touch ID verification
* Even if malware completely compromised my OS, it couldn't sign without my fingerprint

### Git Configuration

Git supports SSH key signing which works with Secretive:

```bash
# Tell Git to use SSH signing format
git config --global gpg.format ssh

# Point to your Secure Enclave key
git config --global user.signingkey ~/.../PublicKeys/your-key.pub

# Don't auto-sign (let the agent commit unsigned)
git config --global commit.gpgsign false
```

The `-S` flag on any commit triggers signing:

```bash
git merge --no-ff -S feature-branch -m "Human approved: new feature"
# → Touch ID prompt appears
```

On the repository side, you can enable, on Github, branch protection rules ensure unsigned commits can't reach the main branch. With these rules, GitHub rejects any push to main that isn't cryptographically signed by a registered key. On GitHub, commits show a green "Verified" badge when the signature matches a key registered to that user's account.

## Challenges

The cryptography is solid, but the signature only proves "a human touched the sensor." not that a "human thought carefully and deliberately as to whether they should touch the sensor". An agent could potentially:

* Ask you to sign while showing a misleading diff
* Request approval with a benign-looking commit message hiding malicious changes
* Prompt rapidly hoping you'll touch without reading

The same "human physically approved this" concept could extend to documents, emails, and other artifacts. The cryptographic primitives are the same—but there's an additional challenge: **key authenticity**.

GitHub solves this for code by being a trusted third party. They verify your email, you upload your public key, they display "Verified" on commits. But if I send you a signed document, how do you know the key is actually mine? Anyone could generate a key and claim it belongs to "Ben Goldhaber."

### Solutions

**Certificate Authorities (PKI)**: The traditional approach. A trusted authority (DigiCert, Let's Encrypt, etc.) verifies your identity and issues a certificate binding your key to your email/organization. This is how S/MIME email signing and Adobe PDF signing work. Recipients trust the signature because they trust the CA.

**Key Publication**: Publish your public key in places you control—your personal website, GitHub profile, DNS records. Verifiers check that the signing key matches what's published at your known domains. Compromising the signature would require compromising multiple accounts.

**Notarization Services**: DocuSign, Adobe Sign, and similar services act as trusted third parties. They verify your identity, record that you signed at a specific time, and embed their own certificate as witness.

For documents shared with people who already know you, simply publishing your key in multiple verifiable locations (GitHub + personal website + company directory) provides reasonable assurance without the overhead of certificate authorities.

## What the Audit Trail Looks Like

After using this workflow, you can get a git history which tells a clear story:

```
main
 │
 ├── abc123 "Merge feature-x" (Signed: carbon-verified) ← Human approved
 │   │
 │   ├── def456 "Add tests" (No signature) ← Agent work
 │   ├── ghi789 "Implement feature" (No signature) ← Agent work
 │   └── jkl012 "Initial scaffold" (No signature) ← Agent work
 │
 ├── mno345 "Merge feature-y" (Signed: carbon-verified) ← Human approved
 ...
```

Anyone auditing the repository can distinguish that merge commits with verified signatures represent human checkpoints. Everything between them is agent-generated work that was reviewed before approval. In practice we'll need other tooling or agents to verify that the approval chain is trusted (humans are too lazy)

## Conclusion

I'm proud of how far and, honestly easy, it was to implement this, and I think its a general workflow pattern I expect we'll want to scale, of utilizing hardware signature commitments, to reflect the ancient pattern that the **signature is a commitment**.

I'd also recommend choosing a cool signing key name. I went with `carbon-verified`, to communicate that a carbon based lifeform approved this message.
