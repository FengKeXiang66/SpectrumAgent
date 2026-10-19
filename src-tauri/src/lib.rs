//! SpectrumAgent process supervision core. The desktop UI is added after core acceptance.

pub mod causality;
pub mod engine_path;
pub mod handshake;
pub mod health;
pub mod logging;
pub mod process;
pub mod state;
pub mod supervisor;
pub mod win32;
#[cfg(debug_assertions)]
pub mod dev_engine;
#[cfg(debug_assertions)]
pub mod datasets_dev;
