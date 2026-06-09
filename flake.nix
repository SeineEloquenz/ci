{
  description = "Nix CI utilities";

  inputs.nixpkgs.url = "github:NixOS/nixpkgs/nixos-unstable";

  outputs =
    { self, nixpkgs }:
    let
      systems = [
        "x86_64-linux"
        "aarch64-linux"
      ];
    in
    {
      packages = nixpkgs.lib.genAttrs systems (system: {
        check-android-versions =
          nixpkgs.legacyPackages.${system}.callPackage ./pkgs/check-android-versions
            { };
      });
    };
}
