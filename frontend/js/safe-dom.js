// Small DOM boundary for data that came from the API, documents, or the model.
// It intentionally uses textContent instead of HTML parsing.
window.AuraSafe = {
    text(element, value) {
        element.textContent = value == null ? '' : String(value);
        return element;
    },
    clear(element) {
        while (element.firstChild) element.removeChild(element.firstChild);
        return element;
    },
    element(tag, className, value) {
        const element = document.createElement(tag);
        if (className) element.className = className;
        if (value !== undefined) this.text(element, value);
        return element;
    }
};
