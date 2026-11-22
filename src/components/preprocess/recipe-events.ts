// Runtime UI projections only; saved recipes stay in the persistent backend database.
export const recipeEvents = new EventTarget();
export const draftEvents = new EventTarget();
export const recipesChanged = () => recipeEvents.dispatchEvent(new Event('change'));
export const draftsChanged = () => draftEvents.dispatchEvent(new Event('change'));
