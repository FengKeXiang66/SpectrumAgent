// Runtime UI projections only; business facts stay in the temporary backend DB.
export const recipeEvents = new EventTarget();
export const draftEvents = new EventTarget();
export const recipesChanged = () => recipeEvents.dispatchEvent(new Event('change'));
export const draftsChanged = () => draftEvents.dispatchEvent(new Event('change'));
