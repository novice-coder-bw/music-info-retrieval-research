# **Music Analysis Platform MVP**

**Author:** Hp Muziq

## **Problem Statement**

Users who work with audio and music production need a faster way to turn a song into an editable production asset. Today, the process of analyzing a track, separating useful stems, selecting the most valuable regions, transcribing them into MIDI, and preparing an Ableton Live project is fragmented and time-consuming. This creates friction for creators who want to move from raw audio to a usable musical workflow without manually stitching together multiple tools.

## **Solution**

Build a minimal web platform that allows a user to upload a song, analyze it for BPM, key, and musical structure, separate stems, and then select one, two, or more regions from the stems for transcription. The platform will generate a lightweight Ableton Live project file that incorporates the extracted analysis metadata, the separated stems, and the resulting MIDI output so the user can continue working in a familiar production environment.

## **User Stories**

> 1. As a music producer, I want to upload a song to the platform, so that I can begin analysis without leaving the browser.  
> 2. As a music producer, I want the platform to analyze my uploaded song for BPM, so that I can align the project to the correct tempo.  
> 3. As a music producer, I want the platform to identify the key of the song, so that I can make musical decisions based on the correct tonal context.  
> 4. As a music producer, I want the platform to detect the song's musical structure, so that I can understand how sections such as intro, verse, chorus, and bridge are organized.  
> 5. As a music producer, I want the platform to separate the song into stems, so that I can work with individual components such as vocals, drums, bass, and other elements.  
> 6. As a music producer, I want to view the stems in a timeline-based interface, so that I can inspect the audio before selecting regions.  
> 7. As a music producer, I want to select one or more regions from the stems, so that I can focus transcription on the most useful musical moments.  
> 8. As a music producer, I want to select exactly the regions I care about, so that I do not waste time transcribing irrelevant portions of the song.  
> 9. As a music producer, I want the system to transcribe my selected regions into MIDI, so that I can use them as editable musical data.  
> 10. As a music producer, I want the platform to create an Ableton Live project file, so that I can continue editing in Ableton without manually setting up the session.  
> 11. As a music producer, I want the exported project to include the extracted BPM and key, so that the session opens with the correct musical context.  
> 12. As a music producer, I want the exported project to include the musical structure metadata, so that I can navigate the arrangement more easily.  
> 13. As a music producer, I want the exported project to include the separated stems, so that I can audition and manipulate the audio sources inside Ableton.  
> 14. As a music producer, I want the exported project to include the transcribed MIDI, so that I can edit notes and timing in a familiar environment.  
> 15. As a music producer, I want the platform to support the most common audio formats for upload, so that I can use files I already have.  
> 16. As a music producer, I want the platform to clearly show the progress of analysis and export tasks, so that I know what is happening while processing occurs.  
> 17. As a music producer, I want the system to preserve my selected regions across the workflow, so that I can review or adjust them before export.  
> 18. As a music producer, I want the platform to make the output usable for a first-pass production workflow, so that I can start editing quickly.  
> 19. As a music producer, I want the platform to be simple enough to use without a heavy setup, so that I can try it with minimal friction.  
> 20. As a music producer, I want the system to produce a lightweight Ableton project scaffold rather than an over-engineered template, so that the output remains practical and editable.

## **Tech Stack & Architecture**

### **Frontend (Client-Side)**

> * **Framework:** Next.js (React)  
> * **Audio Visualization:** WaveSurfer.js  
> * **Styling:** Tailwind CSS (shadcn/ui)  
> * **State Management:** Zustand

### **Backend (API & Orchestration)**

> * **Web Framework:** FastAPI (Python)  
> * **Task Queue & Workers:** Celery \+ Redis  
> * **DAW Assembly:** pyableton

### **AI / Audio Core**

> * **Stem Separation:** Demucs (HTDemucs v4)  
> * **MIDI Transcription:** Basic-Pitch  
> * **Audio Analysis:** madmom (BPM/Beat Tracking), essentia (Key/Structure)

### **Data & Infrastructure**

> * **Database:** Neon Postgres. This serverless database separates storage and compute to offer autoscaling and scale-to-zero capabilities, which is ideal for keeping costs low when there are no queries. It also supports instant branching of the database structure and data, seamlessly syncing with pull requests or temporary agent sessions. Furthermore, it connects efficiently to serverless environments using connection pooling.  
> * **File Storage:** Cloudflare R2.  
> * **Compute (Development):** Lightning AI.  
> * **Compute (Production):** Runpod. This infrastructure utilizes cold-start optimization for serverless endpoints, retaining worker state after scale-down rather than fully tearing down the container, which can reduce infrastructure-level cold starts to as low as 500ms.

## **Implementation Decisions**

> * The platform will be built as a web application with a single primary workflow: upload a song, process it, review the analysis, select regions, transcribe them, and export a project.  
> * The initial version will support WAV and MP3 uploads as the primary input formats to keep the MVP achievable and reliable.  
> * Audio processing will be handled by a FastAPI and Celery backend pipeline that performs analysis, stem separation, region selection support, MIDI transcription, and Ableton project generation.  
> * The analysis stage will extract BPM, musical key, and a simple structural segmentation of the track such as intro, verse, chorus, bridge, and outro where possible.  
> * Stem separation will produce a set of separate audio tracks or files for the main elements of the song, with the exact set determined by the underlying separation model and available processing capabilities.  
> * The user interface will include a timeline-based region selector built with WaveSurfer.js that allows the user to mark one, two, or more regions from the stem playback view.  
> * The selected regions will be treated as the input for the transcription step, rather than transcribing the entire track automatically.  
> * MIDI transcription will be generated only for the selected regions and will be attached to the exported project output.  
> * The exported Ableton Live project will be a lightweight project scaffold that includes metadata, imported stems, and generated MIDI assets rather than a fully automated arrangement template.  
> * The platform will store the analysis result, selected regions, transcription outputs, and export artifacts as part of a single processing session within Neon Postgres and Cloudflare R2.  
> * The processing pipeline will be designed around explicit stages so that each step can be monitored, retried, or improved independently.  
> * The system will expose clear task states for upload, analysis, stem separation, region selection, transcription, and export so the user always knows where the workflow is.

## **Testing Decisions**

> * Good tests should focus on external behavior such as successful upload, correct output artifact generation, and accurate state transitions through the processing workflow.  
> * The core modules to test will include the upload and session orchestration layer, the analysis pipeline, the stem-separation integration, the region-selection workflow, the transcription output generation, and the Ableton project export logic.  
> * Tests should validate that the system produces the expected artifacts for an uploaded song and that the selected regions are preserved through transcription and export.  
> * Prior art for the tests should follow the patterns used for end-to-end workflow systems: input validation, artifact generation, and user-visible state progression rather than internal implementation detail assertions.

## **Out of Scope**

> * Full multi-song batch processing  
> * Fully automated arrangement generation inside Ableton  
> * Advanced mixing, mastering, or production effects generation  
> * Support for every possible audio format or codec  
> * A full-featured music notation or score editor  
> * Real-time collaborative editing

## **Further Notes**

This spec defines the minimum viable version of the platform. The goal is to create a practical first step that turns a song into an editable production workflow with a clear path to expansion later, including better transcription accuracy, richer project templates, and broader format support.