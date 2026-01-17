# coursedata as a git submodule

This package is intended to be used as a git submodule in one or more parent repositories.
It's based on the python library directory in a cookiecutter-data-science (CCDS) project.
I have one project per course per semester, and realized I was copying a lot of code from one
to the other. This should make that process DRY-er.

## Add as a submodule
1) From the parent repo root:
```bash
git submodule add https://github.com/leingang/ccds-coursedata.git coursedata
git submodule update --init --recursive
```
2) Commit the submodule pointer in the parent:
```bash
git add coursedata
git commit -m "Add coursedata submodule"
git push
```

## Make changes in coursedata and publish them
All changes to the submodule live in its own repository. From inside `coursedata/`:
```bash
cd coursedata
git status
# edit files
git add .
git commit -m "Describe coursedata change"
git push origin main
cd ..
```
Then update the parent repo to record the new coursedata commit:
```bash
git add coursedata
git commit -m "Update coursedata submodule"
git push
```

## Pull latest coursedata in another parent repo
From the parent repo root:
```bash
git submodule update --remote coursedata
# or: cd coursedata && git pull && cd ..
git add coursedata
git commit -m "Update coursedata submodule"
git push
```

## Cloning a repo that already uses this submodule
```bash
git clone --recurse-submodules <PARENT_REPO_URL>
# if already cloned:
git submodule update --init --recursive
```

## Notes
- Always push the submodule changes first, then commit the updated pointer in each parent repo.
- `git status` in a parent repo will show coursedata as `modified (new commits)` when the pointer needs committing.
- To make submodules participate in common commands, you can enable: `git config --global submodule.recurse true`.

## Using the VS Code UI
- In the Source Control panel, submodules appear as nested repositories. Open `coursedata` in the panel to stage/commit/push submodule changes, then switch back to the parent repo entry and stage the `coursedata` folder to record the new pointer.
- To pull latest submodule changes: Command Palette → `Git: Update Submodules` (or right-click the submodule in Source Control and pull), then commit the updated `coursedata` pointer in the parent repo entry.
- When cloning, use `Git: Clone (Recursive)` or run `git clone --recurse-submodules`; if already cloned, run `Git: Update Submodules` to initialize.
