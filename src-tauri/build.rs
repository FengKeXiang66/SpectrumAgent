fn main() {
    let attributes = tauri_build::Attributes::new()
        .windows_attributes(
            tauri_build::WindowsAttributes::new()
                .app_manifest(include_str!("windows-app-manifest.xml")),
        )
        .app_manifest(tauri_build::AppManifest::new().commands(&[
            "engine_status",
            "retry_engine",
            "run_smoke",
            "open_data_directory",
            // Permission is declarative; the handler enforces fixed routes and identity.
            "datasets_forward",
        ]));
    if let Err(error) = tauri_build::try_build(attributes) {
        eprintln!("Tauri 构建失败：{error}");
        std::process::exit(1);
    }
}
