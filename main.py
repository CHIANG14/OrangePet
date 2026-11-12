import sys
from pathlib import Path

if __name__ == "__main__":
    if sys.argv[1:] == ["--apply-update"]:
        from orange_pet.updates import apply_update

        raise SystemExit(apply_update(Path(sys.executable).resolve()))

    from orange_pet.app import main

    raise SystemExit(main())
