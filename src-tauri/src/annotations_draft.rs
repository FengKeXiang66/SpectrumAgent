//! TASK-07 12.8: six fixed gesture/draft/export routes. Legacy annotation stays frozen.
pub use crate::agent::{ForwardError, validate_generation};
use crate::{
    agent::{fixed_url, forward_http, invalid_request, uuid},
    handshake::Handshake,
};
use reqwest::{Method, Url};
use serde::Deserialize;
use serde_json::Value;

#[derive(Deserialize)]
#[serde(tag = "op", rename_all = "snake_case", deny_unknown_fields)]
pub enum DraftRequest {
    GetDraft {
        cube_id: String,
    },
    StoreGesture {
        cube_id: String,
        body: Value,
    },
    AddRegion {
        cube_id: String,
        body: Value,
    },
    PatchRegion {
        cube_id: String,
        region_id: String,
        body: Value,
    },

}

pub fn parse_request(value: Value) -> Result<DraftRequest, ForwardError> {
    let request: DraftRequest = serde_json::from_value(value).map_err(|_| invalid_request())?;
    request.validate()?;
    Ok(request)
}

impl DraftRequest {
    fn validate(&self) -> Result<(), ForwardError> {
        let cube_id = match self {
            Self::GetDraft { cube_id }
            | Self::StoreGesture { cube_id, .. }
            | Self::AddRegion { cube_id, .. }
            | Self::PatchRegion { cube_id, .. } => cube_id,
        };
        uuid(cube_id)?;
        match self {
            Self::PatchRegion { region_id, .. }
                if !region_id
                    .strip_prefix("r-")
                    .is_some_and(|id| id.len() >= 4 && id.bytes().all(|c| c.is_ascii_digit())) =>
            {
                return Err(invalid_request());
            }
            _ => {}
        }
        if let Self::AddRegion { body, .. }
        | Self::StoreGesture { body, .. }
        | Self::PatchRegion { body, .. } = self
            && !body.is_object()
        {
            return Err(invalid_request());
        }
        Ok(())
    }

    pub fn destination(&self, port: u16) -> Result<(Url, Method, Option<Value>), ForwardError> {
        self.validate()?;
        let (path, method, body) = match self {
            Self::GetDraft { cube_id } => (
                format!("/api/v1/annotations/{cube_id}/draft"),
                Method::GET,
                None,
            ),
            Self::StoreGesture { cube_id, body } => (
                format!("/api/v1/annotations/{cube_id}/gestures"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::AddRegion { cube_id, body } => (
                format!("/api/v1/annotations/{cube_id}/draft/regions"),
                Method::POST,
                Some(body.clone()),
            ),
            Self::PatchRegion {
                cube_id,
                region_id,
                body,
            } => (
                format!("/api/v1/annotations/{cube_id}/draft/regions/{region_id}"),
                Method::POST,
                Some(body.clone()),
            ),
        };
        Ok((fixed_url(port, &path)?, method, body))
    }
}

pub fn forward(identity: &Handshake, request: &DraftRequest) -> Result<Value, ForwardError> {
    let (url, method, body) = request.destination(identity.port)?;
    forward_http(identity, url, method, body, false, &[])
}

#[cfg(test)]
mod tests {
    use super::*;
    #[test]
    fn version_confirmation_and_mat_download_are_removed() {
        for op in ["confirm","training_mat"] {
            assert!(parse_request(serde_json::json!({"op":op,"cube_id":"00000000-0000-0000-0000-000000000001"})).is_err());
        }
    }
}
