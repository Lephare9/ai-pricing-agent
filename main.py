<!DOCTYPE html>
<html lang="da">
<head>
<meta charset="UTF-8">
<meta name="viewport" content="width=device-width, initial-scale=1.0">

<title>AI Prisagent</title>

<meta http-equiv="Cache-Control" content="no-cache, no-store, must-revalidate">
<meta http-equiv="Pragma" content="no-cache">
<meta http-equiv="Expires" content="0">

<style>

body{
    margin:0;
    padding:0;
    background:#020b1d;
    font-family:Arial,sans-serif;
    color:white;
}

.container{
    max-width:700px;
    margin:auto;
    padding:20px;
}

h1{
    text-align:center;
    font-size:52px;
    line-height:1.05;
    margin-top:30px;
    margin-bottom:20px;
}

.front-text{
    text-align:center;
    font-size:18px;
    line-height:1.5;
    opacity:0.92;
    margin-bottom:30px;
    padding:0 12px;
}

.button-center{
    display:flex;
    justify-content:center;
    margin-bottom:25px;
}

.btn{
    border:none;
    background:#5b8cff;
    color:white;
    font-size:24px;
    font-weight:bold;
    border-radius:28px;
    padding:22px 46px;
    cursor:pointer;
}

.preview-wrap{
    display:flex;
    justify-content:center;
    margin-bottom:25px;
}

.preview{
    width:180px;
    height:180px;
    object-fit:cover;
    border-radius:22px;
    display:none;
}

.loading{
    font-size:28px;
    font-weight:bold;
    text-align:center;
    margin-top:20px;
    animation:pulse 1s infinite;
    display:none;
}

@keyframes pulse{
    0%{opacity:0.35;}
    50%{opacity:1;}
    100%{opacity:0.35;}
}

.result-box{
    background:#08152f;
    border-radius:30px;
    padding:28px;
    margin-top:30px;
}

.result-title{
    font-size:22px;
    line-height:1.4;
    margin-bottom:24px;
}

.result-price{
    font-size:34px;
    font-weight:bold;
}

.similar-wrap{
    display:flex;
    justify-content:center;
    margin-top:30px;
    margin-bottom:30px;
}

.similar-btn{
    background:#5b8cff;
    color:white;
    text-decoration:none;
    padding:16px 30px;
    border-radius:22px;
    font-size:22px;
    font-weight:bold;
    display:inline-block;
}

.error{
    color:white;
    font-size:22px;
    text-align:center;
    margin-top:20px;
}

</style>
</head>

<body>

<div class="container">

<h1>AI Prisagent</h1>

<div id="frontText" class="front-text">
    Tag foto eller vælg fra arkiv og få en prisvurdering.<br><br>
    Prisagenten estimerer brugtpris og linker til lignende varer.
</div>

<div class="button-center">

    <button class="btn" onclick="openPicker()">
        Tag foto
    </button>

</div>

<!-- VIGTIGT:
capture er fjernet
så iPhone åbner:
- fotobibliotek
- tag foto
- vælg arkiv
-->

<input
    type="file"
    id="imageInput"
    accept="image/*"
    style="display:none"
/>

<div class="preview-wrap">
    <img id="preview" class="preview">
</div>

<div id="loading" class="loading">
    Analyserer...
</div>

<div id="result"></div>

</div>

<script>

const API_URL = "https://ai-pricing-agent-production.up.railway.app";

const imageInput = document.getElementById("imageInput");
const preview = document.getElementById("preview");
const loading = document.getElementById("loading");
const result = document.getElementById("result");
const frontText = document.getElementById("frontText");

function openPicker(){

    imageInput.click();
}

imageInput.addEventListener("change", async (e) => {

    const selectedFile = e.target.files[0];

    if(!selectedFile){
        return;
    }

    frontText.style.display = "none";

    result.innerHTML = "";

    preview.src = URL.createObjectURL(selectedFile);
    preview.style.display = "block";

    loading.style.display = "block";

    try{

        const formData = new FormData();

        formData.append("file", selectedFile);

        const response = await fetch(API_URL + "/analyze", {
            method: "POST",
            body: formData
        });

        const data = await response.json();

        loading.style.display = "none";

        if(data.html){

            let searchQuery = "";

            if(data.search_query){
                searchQuery = encodeURIComponent(data.search_query);
            }

            result.innerHTML = `
                ${data.html}

                <div class="similar-wrap">
                    <a
                        class="similar-btn"
                        href="https://www.dba.dk/soeg/?soeg=${searchQuery}"
                        target="_blank"
                    >
                        Se lignende
                    </a>
                </div>
            `;

        }else{

            result.innerHTML = `
                <div class="error">
                    Serverfejl
                </div>
            `;
        }

    }catch(error){

        console.log(error);

        loading.style.display = "none";

        result.innerHTML = `
            <div class="error">
                Serverfejl
            </div>
        `;
    }

});

</script>

</body>
</html>