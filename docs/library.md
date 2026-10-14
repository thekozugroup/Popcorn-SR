# Choose videos from Jellyfin

Popcorn reads the same video folders Jellyfin uses. It does not need Jellyfin credentials, change its database, or copy your library into an import folder. Selecting videos adds references for processing; a worker downloads its own temporary copy. Finished files go to the separate output mount and never replace originals.

1. In **Input → Library**, choose **Movies**, **TV shows**, or your test library.
2. Open the movie folder, or open a show and its season. **Filter this folder** narrows the current folder by name; it does not scan all descendants. **All folders**, breadcrumbs and **Up a folder** let you navigate back.
3. Select individual files or **Select page**. Selections stay when you navigate to another folder or library. **Clear selection** starts over.
4. Set your enhancement and resolution, then use **Preview frame** to compare one frame. Review a short motion sample too before a long job.
5. Use **Run full video**, **Run full batch**, or **Add to queue**. Finished copies appear in **Output queue** and the output folder. Keep testing separate from Jellyfin's watched media folders.

On the owner's Atlas installation, the choices are Test clips, Movies and TV shows. The original movie/show folders are read-only; all results remain under `/mnt/user/Z-Popcorn-SR-Test/output`. Jellyfin will not automatically import these results unless that test folder is added to one of its libraries.

## Docker Compose

Keep the existing `LIBRARY_PATH` and `OUTPUT_PATH` separate. Add the existing Jellyfin host folders to your private `.env`:

```dotenv
POPCORN_LIBRARY_NAME=Test clips
MOVIES_PATH=/path/to/Jellyfin/Movies
TV_PATH=/path/to/Jellyfin/TV-Shows
```

```sh
docker compose -f compose.yaml -f compose.library.yaml up -d manager
```

Both additional mounts are read-only and require existing host folders. The worker does not need these mounts. Include this overlay in future manager recreations.

## Unraid

In the Popcorn SR container's **Edit** form, keep the original `/library`, `/state` and `/output` paths. Add two **Path** entries using the same **host paths** as Jellyfin's movie/show mounts:

| Host folder | Container path | Access |
| --- | --- | --- |
| Existing movie folder | `/sources/movies` | Read Only |
| Existing shows folder | `/sources/shows` | Read Only |

Set the **Additional libraries** variable (`POPCORN_EXTRA_LIBRARIES`) to:

```json
[{"id":"movies","name":"Movies","path":"/sources/movies"},{"id":"shows","name":"TV shows","path":"/sources/shows"}]
```

Apply while the processing queue is idle. Give the original library a friendly name using `POPCORN_LIBRARY_NAME`. Add other video libraries the same way: a read-only Path plus a matching JSON entry. Use a unique lowercase `id` and retain it for existing jobs; paths beginning `@sources/<id>` identify these additional libraries internally. Keep output outside every source folder and avoid removing a mount while its jobs are queued. Folder browsing, filtering, metadata and previews never write into a library.
