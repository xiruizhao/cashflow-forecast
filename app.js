// @ts-check

// handle data encoded in URL search params
const params = new URLSearchParams(window.location.search);
const cfs = params.get("cfs")
if (cfs) {
    localStorage.setItem("cashFlowSeries", cfs);
    console.log("set localstorage from url search " + cfs.length);
    window.location.href = window.location.origin;
}

function copyDataAsUrl() {
    const cfs = localStorage.getItem("cashFlowSeries");
    if (cfs) {
        // cashFlowSeries is python base64.urlsafe_b64encode-ed gzip.compress-ed csv
        // use URLSearchParams to ensure "=" is URL-encoded.
        const params = new URLSearchParams({ cfs: cfs });
        console.log("copyDataAsUrl " + params.toString().length);
        const dataUrl = window.location.origin + "/?" + params.toString();
        if (dataUrl.length <= 2000) {
            navigator.clipboard.writeText(dataUrl);
        } else {
            alert("Your data is too big to be encoded in URL. Please download as a csv file.");
        }
    }
}

function downloadDataAsCsv() {
    const cfs = localStorage.getItem("cashFlowSeries");
    if (cfs) {
        const elem = window.document.createElement('a');
        elem.href = URL.createObjectURL(new Blob([cfs], { type: 'text/csv' }));
        elem.download = `cashflow_series_${(new Date()).toISOString().split('T')[0]}.csv`;
        elem.style.display = 'none';
        document.body.appendChild(elem);
        elem.click();
        document.body.removeChild(elem);
        URL.revokeObjectURL(elem.href);
    }
}

Shiny.initializedPromise.then(() => {
    Shiny.setInputValue("localstorage_cfs", localStorage.getItem("cashFlowSeries"));
    // https://github.com/posit-dev/py-shiny/blob/d656fdb213ea5e48bb54f6627445627e6e49f4b6/shiny/api-examples/session_send_custom_message/app-core.py#L4
    Shiny.addCustomMessageHandler("set_localstorage_cfs", function (message) {
        localStorage.setItem("cashFlowSeries", message);
        console.log("set_localstorage_cfs with " + message.length);
    });
});