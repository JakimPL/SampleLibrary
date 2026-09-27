# Putting your library online

A site shows your library to anyone with its address: the samples of your module collection, the
cloud, and morphs between samples. It shows no folder of your computer, and none of your labels,
ratings or favorites. Samples found only in sample folders you keep private, such as a commercial
pack's, stay on your computer.

These steps put a site on [Railway](https://railway.com). The catalog of a large collection is
several gigabytes, which needs Railway's Pro plan.

## What you need

- The Railway CLI, logged in: `npm install --global @railway/cli`, then `railway login`.
- Your library, built, on this computer.

## Set up the site once

1. **Create a project** in Railway and add a **PostgreSQL** database to it.
2. **Add the site**: a new service from this repository on GitHub. Railway reads `railway.json` and
   builds the `Dockerfile`.
3. **Give it a volume** mounted at `/library`, where the site's audio lives.
4. **Make the reader's password.** The site reads the catalog as a role that may change nothing,
   and its password is generated, never chosen:

   ```sh
   uv run python -c "from samplecore.passwords import new_password; print(new_password())"
   ```

   Keep it in your password manager; you need it each time you publish.
5. **Tell the site where the catalog is.** In the site service's variables, add
   `SAMPLERIPPER_SERVER_DATABASE_URL` with this value, putting the password in:

   ```
   postgresql+psycopg://sampleripper_reader:<the password>@${{Postgres.RAILWAY_PRIVATE_DOMAIN}}:5432/${{Postgres.PGDATABASE}}
   ```

   Then seal the variable, so Railway never shows it again. Add no other database variable: the
   site refuses to start holding any connection that could change the catalog.
6. **Set a spending limit** in the project's usage settings, so a flood of visitors costs no more
   than you chose.
7. **Give the site an address** in its Networking settings.

## Publish

Publishing copies your catalog to the site's database and gathers the site's audio in a folder of
your library, `publication`. Repeat it whenever you want the site to show your library as it is now.

1. **Choose the sample folders the site shows**, if any, in your `config.toml`:

   ```toml
   [publish]
   sample_directories = ["/home/you/Samples/Free Pack"]
   ```

   Your module collection is always published; a sample folder is published only when it is named
   here.
2. **Open the database for a moment:** turn on the PostgreSQL service's public networking (its TCP
   proxy), and copy its `DATABASE_PUBLIC_URL` variable.
3. **Publish**, typing the two secrets where nothing records them:

   ```sh
   read -rs SAMPLERIPPER_PUBLISH_DATABASE_URL && export SAMPLERIPPER_PUBLISH_DATABASE_URL
   read -rs SAMPLERIPPER_PUBLISH_READER_PASSWORD && export SAMPLERIPPER_PUBLISH_READER_PASSWORD
   sampleripper publish
   ```

   The first variable is the `DATABASE_PUBLIC_URL` you copied, the second the reader's password.
   The connection is encrypted, and the password is bound to it. Publishing refuses rather than
   carrying a label, a rating, a favorite or a path of your computer, and changes nothing when it
   refuses.
4. **Close the database again:** turn its public networking off.
5. **Upload the audio** it names to the site's volume. Railway names a volume's files from the
   volume's own root, which the site sees as `/library`:

   ```sh
   railway volume files upload <your library>/publication/objects /objects
   ```

   When you publish again, first run `railway volume files delete /objects`, so the volume holds
   the samples published now and no others.
6. **Restart the site** from its Deployments tab, so it reads the new catalog.

## Check it once it runs

1. **Open the site** at its address, play a few samples and a morph. A sample that won't play
   means the site can't read its volume: Railway's answer is the variable `RAILWAY_RUN_UID=0` on the
   site's service, which runs it as the volume's owner.
2. **Check that each visitor has limits of their own.** This asks for the whole-catalog summary 30
   times, each time claiming to be someone else:

   ```sh
   for i in $(seq 30); do curl -s -o /dev/null -w "%{http_code} " -H "X-Real-IP: 203.0.113.$i" https://<your site>/api/stats; done; echo
   ```

   Some of the last answers should be `429`. If every answer is `200`, the site believes the claim,
   and one visitor could ask without limit: stop the site and don't open it again until this
   check passes.
3. **Check that the database is closed:** the PostgreSQL service's public networking is off.

## Try it on this computer first

`docker compose` runs the same site against a database of its own, which shows what visitors will
see before anything goes online. See [Running it from source](source.md#docker).

## What the site keeps closed

- It reads the catalog as a role Postgres lets change nothing, and starts only with that role.
- It shows no label, rating or favorite, and no folder of your computer.
- Each visitor may ask for only so much, and morphs have budgets of their own.
- Its morph renderer answers the site alone.

[How it works](architecture.md#deployment) describes all of this in detail.
